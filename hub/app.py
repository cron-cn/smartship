from __future__ import annotations

import json
import os
import re
import sqlite3
import shutil
import csv
import io
from functools import wraps
from datetime import datetime
from pathlib import Path
from typing import Iterable

from flask import (
    Flask,
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    send_file,
    send_from_directory,
    session,
    url_for,
)
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "lab_equipment.db"
DEVICES_DIR = DATA_DIR / "devices"
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".xls",
    ".xlsx",
    ".csv",
    ".txt",
    ".zip",
    ".rar",
    ".7z",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
}

DEVICE_STATUS_OPTIONS = ["拟采购", "已采购，未入库", "已入库"]

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "lab-equipment-manager")
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
DEFAULT_PAGE_SIZE = 6


def ensure_runtime_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DEVICES_DIR.mkdir(parents=True, exist_ok=True)


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        ensure_runtime_dirs()
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


@app.teardown_appcontext
def close_db(exception: Exception | None) -> None:
    database = g.pop("db", None)
    if database is not None:
        database.close()


def init_db() -> None:
    ensure_runtime_dirs()
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_code TEXT,
                device_name TEXT NOT NULL,
                voltage TEXT,
                current TEXT,
                quantity TEXT,
                quantity_normal TEXT,
                quantity_broken TEXT,
                broken_details TEXT,
                device_status TEXT,
                remarks TEXT,
                purchase_link TEXT,
                folder_name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id INTEGER NOT NULL,
                kind TEXT NOT NULL,
                original_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                relative_path TEXT NOT NULL,
                mime_type TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS device_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_name TEXT NOT NULL,
                folder_name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS device_group_devices (
                group_id INTEGER NOT NULL,
                device_id INTEGER NOT NULL,
                PRIMARY KEY (group_id, device_id),
                FOREIGN KEY (group_id) REFERENCES device_groups(id) ON DELETE CASCADE,
                FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
            );
            """
        )
        ensure_device_columns(connection)
        ensure_group_tables(connection)
        connection.commit()
    finally:
        connection.close()


def ensure_device_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(devices)").fetchall()
    }
    required_columns = {
        "device_code": "TEXT",
        "quantity_normal": "TEXT",
        "quantity_broken": "TEXT",
        "broken_details": "TEXT",
        "device_status": "TEXT",
    }
    for column_name, column_type in required_columns.items():
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE devices ADD COLUMN {column_name} {column_type}")

    connection.execute(
        """
        UPDATE devices
        SET quantity_normal = COALESCE(quantity_normal, quantity),
            quantity_broken = COALESCE(quantity_broken, '0'),
            broken_details = COALESCE(broken_details, '[]'),
            device_status = COALESCE(device_status, ?)
        """,
        (DEVICE_STATUS_OPTIONS[0],),
    )
    connection.execute(
        """
        UPDATE devices
        SET device_code = CAST(id AS TEXT)
        WHERE device_code IS NULL OR TRIM(device_code) = ''
        """
    )


def ensure_group_tables(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS device_groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_name TEXT NOT NULL,
            folder_name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS device_group_devices (
            group_id INTEGER NOT NULL,
            device_id INTEGER NOT NULL,
            PRIMARY KEY (group_id, device_id),
            FOREIGN KEY (group_id) REFERENCES device_groups(id) ON DELETE CASCADE,
            FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE
        )
        """
    )


def normalize_status(value: str | None) -> str:
    value = normalize_text(value)
    return value if value in DEVICE_STATUS_OPTIONS else DEVICE_STATUS_OPTIONS[0]


def normalize_group_name(value: str | None) -> str:
    value = normalize_text(value)
    return value or "未命名分类"


def can_edit() -> bool:
    # 取消密码保护：始终允许编辑
    return True


def require_edit_permission(view_func):
    @wraps(view_func)
    def wrapped_view(*args, **kwargs):
        if not can_edit():
            flash("需要输入密码才能修改。", "error")
            return redirect(url_for("index"))
        return view_func(*args, **kwargs)

    return wrapped_view


@app.route("/unlock", methods=["POST"])
def unlock_editing():
    # 已移除密码要求：直接允许解锁（保留路由以兼容旧客户端）
    session["can_edit"] = True
    flash("已解锁编辑模式（无需密码）。", "success")
    return redirect(url_for("devices_page"))


@app.route("/lock", methods=["POST"])
def lock_editing():
    session["can_edit"] = False
    flash("已切换为只读模式。", "success")
    return redirect(url_for("index"))


def validate_broken_image_uploads(files) -> str | None:
    for key in files.keys():
        if re.match(r"^broken_image_\d+$", key):
            upload = files.get(key)
            if upload and upload.filename and not allowed_file(upload.filename or "", ALLOWED_IMAGE_EXTENSIONS):
                return "损坏配件图片格式不支持，请使用 jpg、png、gif、webp 或 bmp。"
    return None


def load_json_list(raw_value: str | None) -> list[dict[str, object]]:
    if not raw_value:
        return []
    try:
        parsed = json.loads(raw_value)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


@app.before_request
def bootstrap() -> None:
    init_db()


def normalize_text(value: str | None) -> str:
    return (value or "").strip()


def slugify(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value.lower()[:40] or "device"


def allowed_file(filename: str, allowed_extensions: Iterable[str]) -> bool:
    return Path(filename).suffix.lower() in allowed_extensions


def save_uploaded_file(upload, target_dir: Path, kind: str, device_id: int) -> dict[str, str]:
    original_name = secure_filename(upload.filename or "")
    if not original_name:
        raise ValueError("文件名无效")

    extension = Path(original_name).suffix.lower()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
    stored_name = f"{kind}_{device_id}_{timestamp}{extension}"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / stored_name
    upload.save(file_path)

    relative_path = file_path.relative_to(BASE_DIR).as_posix()
    return {
        "original_name": original_name,
        "stored_name": stored_name,
        "relative_path": relative_path,
        "mime_type": upload.mimetype or "",
    }


def save_bytes_file(content: bytes, original_name: str, target_dir: Path, kind: str, device_id: int) -> dict[str, str]:
    target_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{kind}_{device_id}_{datetime.now().strftime('%Y%m%d%H%M%S%f')}{Path(original_name).suffix.lower()}"
    file_path = target_dir / stored_name
    file_path.write_bytes(content)
    return {
        "original_name": original_name,
        "stored_name": stored_name,
        "relative_path": file_path.relative_to(BASE_DIR).as_posix(),
        "mime_type": "text/csv",
    }


def device_storage_dir(folder_name: str) -> Path:
    return DEVICES_DIR / folder_name


def categories_storage_dir() -> Path:
    path = DATA_DIR / "categories"
    path.mkdir(parents=True, exist_ok=True)
    return path


def category_storage_dir(folder_name: str) -> Path:
    return categories_storage_dir() / folder_name


def get_device_categories(database: sqlite3.Connection, device_id: int) -> list[sqlite3.Row]:
    return database.execute(
        """
        SELECT g.id, g.group_name, g.folder_name
        FROM device_groups g
        JOIN device_group_devices gd ON gd.group_id = g.id
        WHERE gd.device_id = ?
        ORDER BY g.id ASC
        """,
        (device_id,),
    ).fetchall()


def write_category_metadata(category_row: sqlite3.Row) -> None:
    category_dir = category_storage_dir(category_row["folder_name"])
    category_dir.mkdir(parents=True, exist_ok=True)
    with (category_dir / "metadata.json").open("w", encoding="utf-8") as metadata_file:
        json.dump(
            {
                "id": category_row["id"],
                "group_name": category_row["group_name"],
                "folder_name": category_row["folder_name"],
                "created_at": category_row["created_at"],
            },
            metadata_file,
            ensure_ascii=False,
            indent=2,
        )


def fetch_categories() -> list[dict[str, object]]:
    database = get_db()
    rows = database.execute(
        """
        SELECT g.id, g.group_name, g.folder_name, g.created_at, COUNT(gd.device_id) AS device_count
        FROM device_groups g
        LEFT JOIN device_group_devices gd ON gd.group_id = g.id
        GROUP BY g.id
        ORDER BY g.id DESC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_device_choices() -> list[dict[str, object]]:
    database = get_db()
    rows = database.execute(
        """
        SELECT id, device_code, device_name
        FROM devices
        ORDER BY id ASC
        """
    ).fetchall()
    return [dict(row) for row in rows]


def fetch_device_sidebar_choices(category_id: int | None = None) -> list[dict[str, object]]:
    database = get_db()
    if category_id is None:
        rows = database.execute(
            """
            SELECT id, device_code, device_name
            FROM devices
            ORDER BY id ASC
            """
        ).fetchall()
    else:
        rows = database.execute(
            """
            SELECT d.id, d.device_code, d.device_name
            FROM devices d
            JOIN device_group_devices gd ON gd.device_id = d.id
            WHERE gd.group_id = ?
            ORDER BY d.id ASC
            """,
            (category_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def fetch_device_order_ids(category_id: int | None = None) -> list[int]:
    database = get_db()
    if category_id is None:
        rows = database.execute("SELECT id FROM devices ORDER BY id ASC").fetchall()
    else:
        rows = database.execute(
            """
            SELECT d.id
            FROM devices d
            JOIN device_group_devices gd ON gd.device_id = d.id
            WHERE gd.group_id = ?
            ORDER BY d.id ASC
            """,
            (category_id,),
        ).fetchall()
    return [row["id"] for row in rows]


def get_device_navigation(device_id: int, category_id: int | None = None) -> dict[str, int | None]:
    ordered_ids = fetch_device_order_ids(category_id=category_id)
    if device_id not in ordered_ids:
        return {"previous_id": None, "next_id": None}

    index = ordered_ids.index(device_id)
    previous_id = ordered_ids[index - 1] if index > 0 else None
    next_id = ordered_ids[index + 1] if index < len(ordered_ids) - 1 else None
    return {"previous_id": previous_id, "next_id": next_id}


def fetch_device_detail(device_id: int) -> dict[str, object] | None:
    database = get_db()
    row = database.execute(
        """
        SELECT
            id,
            device_code,
            device_name,
            voltage,
            current,
            quantity,
            quantity_normal,
            quantity_broken,
            broken_details,
            device_status,
            remarks,
            purchase_link,
            folder_name,
            created_at
        FROM devices
        WHERE id = ?
        """,
        (device_id,),
    ).fetchone()
    if row is None:
        return None

    files = database.execute(
        """
        SELECT
            id,
            kind,
            original_name,
            relative_path
        FROM device_files
        WHERE device_id = ?
        ORDER BY id ASC
        """,
        (device_id,),
    ).fetchall()
    images = [dict(file) for file in files if file["kind"] == "image"]
    attachments = [dict(file) for file in files if file["kind"] == "attachment"]
    broken_images = [dict(file) for file in files if file["kind"] == "broken_image"]
    broken_details = load_json_list(row["broken_details"])
    broken_items = []
    for index, item in enumerate(broken_details, start=1):
        image_file_id = item.get("image_file_id")
        image_file = next((file for file in broken_images if file["id"] == image_file_id), None)
        broken_items.append(
            {
                "index": index,
                "reason": normalize_text(str(item.get("reason", ""))),
                "image_file_id": image_file_id,
                "image_original_name": image_file["original_name"] if image_file else "",
            }
        )

    return {
        **dict(row),
        "display_name": row["device_name"] or f"未命名设备#{row['id']}",
        "images": images,
        "attachments": attachments,
        "broken_items": broken_items,
        "device_status": normalize_status(row["device_status"]),
        "categories": [dict(category) for category in get_device_categories(database, device_id)],
    }


def upsert_device_files(database: sqlite3.Connection, device_id: int, uploads, target_dir: Path, kind: str, created_at: str) -> None:
    for upload in uploads:
        file_meta = save_uploaded_file(upload, target_dir, kind, device_id)
        database.execute(
            """
            INSERT INTO device_files (
                device_id,
                kind,
                original_name,
                stored_name,
                relative_path,
                mime_type,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_id,
                kind,
                file_meta["original_name"],
                file_meta["stored_name"],
                file_meta["relative_path"],
                file_meta["mime_type"],
                created_at,
            ),
        )


def collect_broken_entries_from_request(form, files) -> list[dict[str, object]]:
    reason_entries: dict[int, str] = {}
    image_entries: dict[int, object] = {}

    for key in form.keys():
        match = re.match(r"^broken_reason_(\d+)$", key)
        if match:
            reason_entries[int(match.group(1))] = normalize_text(form.get(key))

    for key in files.keys():
        match = re.match(r"^broken_image_(\d+)$", key)
        if match:
            image_entries[int(match.group(1))] = files.get(key)

    broken_entries: list[dict[str, object]] = []
    for index in sorted(set(reason_entries) | set(image_entries)):
        broken_entries.append(
            {
                "index": index,
                "reason": reason_entries.get(index, ""),
                "image_upload": image_entries.get(index),
            }
        )
    return broken_entries


def save_broken_entries(
    database: sqlite3.Connection,
    device_id: int,
    broken_entries: list[dict[str, object]],
    broken_dir: Path,
    created_at: str,
) -> list[dict[str, object]]:
    broken_items: list[dict[str, object]] = []
    for entry in broken_entries:
        normalized_reason = normalize_text(str(entry.get("reason", "")))
        image_upload = entry.get("image_upload")
        image_file_id = None
        image_original_name = ""
        if image_upload and getattr(image_upload, "filename", ""):
            if not allowed_file(image_upload.filename or "", ALLOWED_IMAGE_EXTENSIONS):
                continue
            file_meta = save_uploaded_file(image_upload, broken_dir, "broken_image", device_id)
            cursor = database.execute(
                """
                INSERT INTO device_files (
                    device_id,
                    kind,
                    original_name,
                    stored_name,
                    relative_path,
                    mime_type,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    device_id,
                    "broken_image",
                    file_meta["original_name"],
                    file_meta["stored_name"],
                    file_meta["relative_path"],
                    file_meta["mime_type"],
                    created_at,
                ),
            )
            image_file_id = cursor.lastrowid
            image_original_name = file_meta["original_name"]

        if not normalized_reason and image_file_id is None:
            continue

        broken_items.append(
            {
                "reason": normalized_reason,
                "image_file_id": image_file_id,
                "image_original_name": image_original_name,
            }
        )
    return broken_items


def merge_broken_details(existing: str | None, new_items: list[dict[str, object]]) -> str:
    existing_items = load_json_list(existing)
    merged_items = [item for item in existing_items if isinstance(item, dict)]
    merged_items.extend(new_items)
    return json.dumps(merged_items, ensure_ascii=False)


def rebuild_metadata(device_row: sqlite3.Row, database: sqlite3.Connection) -> None:
    files = database.execute(
        "SELECT id, kind, original_name, relative_path FROM device_files WHERE device_id = ? ORDER BY id ASC",
        (device_row["id"],),
    ).fetchall()
    file_index = {file_row["id"]: dict(file_row) for file_row in files}
    broken_details = load_json_list(device_row["broken_details"])
    broken_items: list[dict[str, object]] = []
    for index, item in enumerate(broken_details, start=1):
        image_file_id = item.get("image_file_id")
        image_file = file_index.get(image_file_id) if isinstance(image_file_id, int) else None
        broken_items.append(
            {
                "index": index,
                "reason": normalize_text(str(item.get("reason", ""))),
                "image_file_id": image_file_id,
                "image_original_name": image_file["original_name"] if image_file else "",
                "image_relative_path": image_file["relative_path"] if image_file else "",
            }
        )
    metadata = {
        "id": device_row["id"],
        "device_code": device_row["device_code"],
        "device_name": device_row["device_name"],
        "display_name": device_row["device_name"] or f"未命名设备#{device_row['id']}",
        "voltage": device_row["voltage"],
        "current": device_row["current"],
        "quantity_normal": device_row["quantity_normal"],
        "quantity_broken": device_row["quantity_broken"],
        "broken_details": broken_items,
        "device_status": device_row["device_status"],
        "remarks": device_row["remarks"],
        "purchase_link": device_row["purchase_link"],
        "folder_name": device_row["folder_name"],
        "created_at": device_row["created_at"],
        "images": [dict(file) for file in files if file["kind"] == "image"],
        "attachments": [dict(file) for file in files if file["kind"] == "attachment"],
        "broken_images": [dict(file) for file in files if file["kind"] == "broken_image"],
    }
    device_dir = device_storage_dir(device_row["folder_name"])
    device_dir.mkdir(parents=True, exist_ok=True)
    with (device_dir / "metadata.json").open("w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, ensure_ascii=False, indent=2)


def fetch_devices(page: int = 1, page_size: int | None = DEFAULT_PAGE_SIZE, category_id: int | None = None) -> tuple[list[dict[str, object]], int, int]:
    database = get_db()
    if category_id is None:
        total = database.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    else:
        total = database.execute(
            """
            SELECT COUNT(*)
            FROM devices d
            JOIN device_group_devices gd ON gd.device_id = d.id
            WHERE gd.group_id = ?
            """,
            (category_id,),
        ).fetchone()[0]
    if page_size is None or page_size <= 0:
        page_size = max(total, 1)

    total_pages = max((total + page_size - 1) // page_size, 1) if total else 1
    page = max(1, min(page, total_pages))
    offset = (page - 1) * page_size
    if category_id is None:
        rows = database.execute(
            """
            SELECT
                id,
                device_code,
                device_name,
                voltage,
                current,
                quantity,
                quantity_normal,
                quantity_broken,
                broken_details,
                device_status,
                remarks,
                purchase_link,
                folder_name,
                created_at
            FROM devices
            ORDER BY id ASC
            LIMIT ? OFFSET ?
            """,
            (page_size, offset),
        ).fetchall()
    else:
        rows = database.execute(
            """
            SELECT
                d.id,
                d.device_code,
                d.device_name,
                d.voltage,
                d.current,
                d.quantity,
                d.quantity_normal,
                d.quantity_broken,
                d.broken_details,
                d.device_status,
                d.remarks,
                d.purchase_link,
                d.folder_name,
                d.created_at
            FROM devices d
            JOIN device_group_devices gd ON gd.device_id = d.id
            WHERE gd.group_id = ?
            ORDER BY d.id ASC
            LIMIT ? OFFSET ?
            """,
            (category_id, page_size, offset),
        ).fetchall()

    devices: list[dict[str, object]] = []
    for row in rows:
        files = database.execute(
            """
            SELECT
                id,
                kind,
                original_name,
                relative_path
            FROM device_files
            WHERE device_id = ?
            ORDER BY id ASC
            """,
            (row["id"],),
        ).fetchall()
        images = [dict(file) for file in files if file["kind"] == "image"]
        attachments = [dict(file) for file in files if file["kind"] == "attachment"]
        broken_images = [dict(file) for file in files if file["kind"] == "broken_image"]
        broken_details = load_json_list(row["broken_details"])
        broken_items = []
        for index, item in enumerate(broken_details, start=1):
            image_file_id = item.get("image_file_id")
            image_file = next((file for file in broken_images if file["id"] == image_file_id), None)
            broken_items.append(
                {
                    "index": index,
                    "reason": normalize_text(str(item.get("reason", ""))),
                    "image_file_id": image_file_id,
                    "image_original_name": image_file["original_name"] if image_file else "",
                }
            )
        display_name = row["device_name"] or f"未命名设备#{row['id']}"
        devices.append(
            {
                **dict(row),
                "display_name": display_name,
                "images": images,
                "attachments": attachments,
                "broken_items": broken_items,
                "device_status": normalize_status(row["device_status"]),
                "categories": [dict(category) for category in get_device_categories(database, row["id"])],
            }
        )
    return devices, page, total_pages


@app.route("/", methods=["GET"])
def index():
    database = get_db()
    device_count = database.execute("SELECT COUNT(*) FROM devices").fetchone()[0]
    category_count = database.execute("SELECT COUNT(*) FROM device_groups").fetchone()[0]
    return render_template(
        "home.html",
        can_edit=can_edit(),
        device_count=device_count,
        category_count=category_count,
    )


@app.route("/devices", methods=["GET"])
def devices_page():
    category_id = request.args.get("category_id", type=int)
    device_id = request.args.get("device_id", type=int)
    if can_edit():
        devices, _, _ = fetch_devices(page=1, page_size=None, category_id=category_id)
        page = 1
        total_pages = 1
    else:
        page = request.args.get("page", default=1, type=int)
        devices, page, total_pages = fetch_devices(page=page, category_id=category_id)

    sidebar_devices = fetch_device_sidebar_choices(category_id=category_id)
    if device_id is None and sidebar_devices:
        device_id = sidebar_devices[0]["id"]

    device = fetch_device_detail(device_id) if device_id is not None else None
    if device is None and sidebar_devices:
        device = fetch_device_detail(sidebar_devices[0]["id"])
        device_id = sidebar_devices[0]["id"]
    if device is None:
        device = {
            "id": None,
            "device_code": "",
            "display_name": "没有可显示的设备",
            "device_status": "",
            "folder_name": "",
            "voltage": "",
            "current": "",
            "quantity_normal": "",
            "quantity_broken": "",
            "broken_items": [],
            "remarks": "",
            "purchase_link": "",
            "categories": [],
            "images": [],
            "attachments": [],
        }

    return render_template(
        "device_detail.html",
        device=device,
        can_edit=can_edit(),
        category_id=category_id,
        navigation=get_device_navigation(device_id, category_id=category_id) if device_id is not None else {"previous_id": None, "next_id": None},
        sidebar_devices=sidebar_devices,
        devices_page_devices=devices,
        devices_page=page,
        devices_total_pages=total_pages,
    )


@app.route("/edit-devices", methods=["GET"])
def edit_devices_page():
    if not can_edit():
        return render_template("edit_gate.html", can_edit=can_edit())

    devices, _, _ = fetch_devices(page=1, page_size=None)
    return render_template(
        "index.html",
        devices=devices,
        page=1,
        total_pages=1,
        page_size=DEFAULT_PAGE_SIZE,
        autosave_key="lab-equipment-draft",
        can_edit=True,
        categories=fetch_categories(),
        selected_category_id=None,
        all_devices=fetch_device_choices(),
    )


@app.route("/categories", methods=["GET"])
def categories_page():
    return render_template(
        "categories.html",
        can_edit=can_edit(),
        categories=fetch_categories(),
        all_devices=fetch_device_choices(),
    )


@app.route("/device/<int:device_id>", methods=["GET"])
def device_detail_page(device_id: int):
    category_id = request.args.get("category_id", type=int)
    device = fetch_device_detail(device_id)
    if device is None:
        abort(404)
    return render_template(
        "device_detail.html",
        device=device,
        can_edit=can_edit(),
        category_id=category_id,
        navigation=get_device_navigation(device_id, category_id=category_id),
        sidebar_devices=fetch_device_sidebar_choices(category_id=category_id),
    )


@app.route("/add", methods=["POST"])
@require_edit_permission
def add_device():
    device_code = normalize_text(request.form.get("device_code"))
    device_name = normalize_text(request.form.get("device_name"))
    voltage = normalize_text(request.form.get("voltage"))
    current = normalize_text(request.form.get("current"))
    quantity_normal = normalize_text(request.form.get("quantity_normal"))
    quantity_broken = normalize_text(request.form.get("quantity_broken"))
    remarks = normalize_text(request.form.get("remarks"))
    purchase_link = normalize_text(request.form.get("purchase_link"))
    device_status = normalize_status(request.form.get("device_status"))

    image_uploads = [file for file in request.files.getlist("images") if file and file.filename]
    attachment_uploads = [file for file in request.files.getlist("attachments") if file and file.filename]
    broken_entries = collect_broken_entries_from_request(request.form, request.files)
    broken_image_error = validate_broken_image_uploads(request.files)
    if broken_image_error:
        flash(broken_image_error, "error")
        return redirect(url_for("devices_page"))

    if len(image_uploads) > 3:
        flash("图片最多只能上传 3 张。", "error")
        return redirect(url_for("devices_page"))

    for upload in image_uploads:
        if not allowed_file(upload.filename or "", ALLOWED_IMAGE_EXTENSIONS):
            flash("图片格式不支持，请使用 jpg、png、gif、webp 或 bmp。", "error")
            return redirect(url_for("devices_page"))

    for upload in attachment_uploads:
        if not allowed_file(upload.filename or "", ALLOWED_ATTACHMENT_EXTENSIONS):
            flash("附件格式不支持。", "error")
            return redirect(url_for("devices_page"))

    database = get_db()
    created_at = datetime.now().isoformat(timespec="seconds")
    display_name = device_name or "未命名设备"
    placeholder_slug = slugify(device_name or f"device-{created_at}")
    cursor = database.execute(
        """
        INSERT INTO devices (
            device_code,
            device_name,
            voltage,
            current,
            quantity,
            quantity_normal,
            quantity_broken,
            broken_details,
            device_status,
            remarks,
            purchase_link,
            folder_name,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            device_code,
            device_name,
            voltage,
            current,
            quantity_normal,
            quantity_normal,
            quantity_broken,
            "[]",
            device_status,
            remarks,
            purchase_link,
            f"pending-{placeholder_slug}",
            created_at,
        ),
    )
    device_id = cursor.lastrowid
    folder_name = f"device_{device_id}_{placeholder_slug}"
    device_dir = DEVICES_DIR / folder_name
    image_dir = device_dir / "images"
    attachment_dir = device_dir / "attachments"
    device_dir.mkdir(parents=True, exist_ok=True)
    image_dir.mkdir(parents=True, exist_ok=True)
    attachment_dir.mkdir(parents=True, exist_ok=True)
    broken_dir = device_dir / "broken"
    broken_dir.mkdir(parents=True, exist_ok=True)

    database.execute(
        "UPDATE devices SET folder_name = ? WHERE id = ?",
        (folder_name, device_id),
    )

    broken_items = save_broken_entries(database, device_id, broken_entries, broken_dir, created_at)
    database.execute(
        "UPDATE devices SET broken_details = ? WHERE id = ?",
        (json.dumps(broken_items, ensure_ascii=False), device_id),
    )

    metadata = {
        "id": device_id,
        "device_code": device_code,
        "device_name": device_name,
        "display_name": device_name or f"未命名设备#{device_id}",
        "voltage": voltage,
        "current": current,
        "quantity_normal": quantity_normal,
        "quantity_broken": quantity_broken,
        "broken_details": broken_items,
        "device_status": device_status,
        "remarks": remarks,
        "purchase_link": purchase_link,
        "folder_name": folder_name,
        "created_at": created_at,
    }
    with (device_dir / "metadata.json").open("w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, ensure_ascii=False, indent=2)

    upsert_device_files(database, device_id, image_uploads, image_dir, "image", created_at)
    upsert_device_files(database, device_id, attachment_uploads, attachment_dir, "attachment", created_at)
    # 处理表单中的分类标签（将设备加入选中的目录）
    try:
        category_ids = [int(v) for v in request.form.getlist('category_ids') if str(v).isdigit()]
    except Exception:
        category_ids = []

    for group_id in category_ids:
        exists = database.execute("SELECT 1 FROM device_groups WHERE id = ?", (group_id,)).fetchone()
        if exists:
            database.execute(
                "INSERT OR IGNORE INTO device_group_devices (group_id, device_id) VALUES (?, ?)",
                (group_id, device_id),
            )

    # 更新被影响分类的 metadata.json
    affected_groups = set(category_ids)
    for gid in affected_groups:
        group_row = database.execute("SELECT * FROM device_groups WHERE id = ?", (gid,)).fetchone()
        if group_row:
            all_device_ids_in_group = [r[0] for r in database.execute("SELECT device_id FROM device_group_devices WHERE group_id = ?", (gid,)).fetchall()]
            group_dir = category_storage_dir(group_row["folder_name"]) if group_row["folder_name"] else categories_storage_dir()
            group_dir.mkdir(parents=True, exist_ok=True)
            with (group_dir / "metadata.json").open("w", encoding="utf-8") as metadata_file:
                json.dump(
                    {
                        "id": group_row["id"],
                        "group_name": group_row["group_name"],
                        "folder_name": group_row["folder_name"],
                        "device_ids": all_device_ids_in_group,
                        "created_at": group_row["created_at"],
                    },
                    metadata_file,
                    ensure_ascii=False,
                    indent=2,
                )

    database.commit()
    flash(f"设备 {display_name} 已保存，并已创建独立文件夹 {folder_name}。", "success")
    return redirect(url_for("edit_devices_page"))


@app.route("/edit/<int:device_id>", methods=["POST"])
@require_edit_permission
def edit_device(device_id: int):
    database = get_db()
    device_row = database.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if device_row is None:
        flash("设备不存在。", "error")
        return redirect(url_for("devices_page"))

    device_code = normalize_text(request.form.get("device_code"))
    device_name = normalize_text(request.form.get("device_name"))
    voltage = normalize_text(request.form.get("voltage"))
    current = normalize_text(request.form.get("current"))
    quantity_normal = normalize_text(request.form.get("quantity_normal"))
    quantity_broken = normalize_text(request.form.get("quantity_broken"))
    remarks = normalize_text(request.form.get("remarks"))
    purchase_link = normalize_text(request.form.get("purchase_link"))
    device_status = normalize_status(request.form.get("device_status"))

    image_uploads = [file for file in request.files.getlist("images") if file and file.filename]
    attachment_uploads = [file for file in request.files.getlist("attachments") if file and file.filename]
    broken_entries = collect_broken_entries_from_request(request.form, request.files)
    broken_image_error = validate_broken_image_uploads(request.files)
    if broken_image_error:
        flash(broken_image_error, "error")
        return redirect(url_for("devices_page"))

    current_images = database.execute(
        "SELECT COUNT(*) FROM device_files WHERE device_id = ? AND kind = 'image'",
        (device_id,),
    ).fetchone()[0]
    if current_images + len(image_uploads) > 3:
        flash("图片总数最多只能保留 3 张。", "error")
        return redirect(url_for("devices_page"))

    for upload in image_uploads:
        if not allowed_file(upload.filename or "", ALLOWED_IMAGE_EXTENSIONS):
            flash("图片格式不支持，请使用 jpg、png、gif、webp 或 bmp。", "error")
            return redirect(url_for("devices_page"))

    for upload in attachment_uploads:
        if not allowed_file(upload.filename or "", ALLOWED_ATTACHMENT_EXTENSIONS):
            flash("附件格式不支持。", "error")
            return redirect(url_for("devices_page"))

    folder_name = device_row["folder_name"]
    device_dir = device_storage_dir(folder_name)
    image_dir = device_dir / "images"
    attachment_dir = device_dir / "attachments"

    database.execute(
        """
        UPDATE devices
        SET device_code = ?, device_name = ?, voltage = ?, current = ?, quantity = ?, quantity_normal = ?, quantity_broken = ?, device_status = ?, remarks = ?, purchase_link = ?
        WHERE id = ?
        """,
        (
            device_code,
            device_name,
            voltage,
            current,
            quantity_normal,
            quantity_normal,
            quantity_broken,
            device_status,
            remarks,
            purchase_link,
            device_id,
        ),
    )

    now = datetime.now().isoformat(timespec="seconds")
    upsert_device_files(database, device_id, image_uploads, image_dir, "image", now)
    upsert_device_files(database, device_id, attachment_uploads, attachment_dir, "attachment", now)

    broken_dir = device_dir / "broken"
    broken_dir.mkdir(parents=True, exist_ok=True)
    new_broken_items = save_broken_entries(database, device_id, broken_entries, broken_dir, now)
    existing_broken = device_row["broken_details"]
    merged_broken_details = merge_broken_details(existing_broken, new_broken_items)
    database.execute(
        "UPDATE devices SET broken_details = ? WHERE id = ?",
        (merged_broken_details, device_id),
    )
    # 处理分类标签：同步 device_group_devices（删除未选的、添加新选的）
    try:
        selected_ids = {int(v) for v in request.form.getlist('category_ids') if str(v).isdigit()}
    except Exception:
        selected_ids = set()

    existing_rows = database.execute("SELECT group_id FROM device_group_devices WHERE device_id = ?", (device_id,)).fetchall()
    existing_ids = {r[0] for r in existing_rows}

    # 删除不再选中的
    to_remove = existing_ids - selected_ids
    for gid in to_remove:
        database.execute("DELETE FROM device_group_devices WHERE group_id = ? AND device_id = ?", (gid, device_id))

    # 添加新选中的
    to_add = selected_ids - existing_ids
    for gid in to_add:
        exists = database.execute("SELECT 1 FROM device_groups WHERE id = ?", (gid,)).fetchone()
        if exists:
            database.execute("INSERT OR IGNORE INTO device_group_devices (group_id, device_id) VALUES (?, ?)", (gid, device_id))

    # 更新受影响分类的 metadata.json
    affected = existing_ids.union(selected_ids)
    for gid in affected:
        group_row = database.execute("SELECT * FROM device_groups WHERE id = ?", (gid,)).fetchone()
        if group_row:
            all_device_ids_in_group = [r[0] for r in database.execute("SELECT device_id FROM device_group_devices WHERE group_id = ?", (gid,)).fetchall()]
            group_dir = category_storage_dir(group_row["folder_name"]) if group_row["folder_name"] else categories_storage_dir()
            group_dir.mkdir(parents=True, exist_ok=True)
            with (group_dir / "metadata.json").open("w", encoding="utf-8") as metadata_file:
                json.dump(
                    {
                        "id": group_row["id"],
                        "group_name": group_row["group_name"],
                        "folder_name": group_row["folder_name"],
                        "device_ids": all_device_ids_in_group,
                        "created_at": group_row["created_at"],
                    },
                    metadata_file,
                    ensure_ascii=False,
                    indent=2,
                )

    database.commit()

    updated_row = database.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    if updated_row is not None:
        rebuild_metadata(updated_row, database)

    flash(f"设备 {device_name or f'未命名设备#{device_id}'} 已更新。", "success")
    page = request.form.get("page", default=1, type=int)
    return redirect(url_for("edit_devices_page"))


@app.route("/draft/save", methods=["POST"])
@require_edit_permission
def save_draft():
    payload = request.get_json(silent=True) or {}
    draft_path = DATA_DIR / "draft.json"
    with draft_path.open("w", encoding="utf-8") as draft_file:
        json.dump(
            {
                "device_name": normalize_text(payload.get("device_name")),
                "voltage": normalize_text(payload.get("voltage")),
                "current": normalize_text(payload.get("current")),
                "quantity_normal": normalize_text(payload.get("quantity_normal")),
                "quantity_broken": normalize_text(payload.get("quantity_broken")),
                "remarks": normalize_text(payload.get("remarks")),
                "purchase_link": normalize_text(payload.get("purchase_link")),
                "device_status": normalize_status(payload.get("device_status")),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            },
            draft_file,
            ensure_ascii=False,
            indent=2,
        )
    return {"ok": True}


@app.route("/import", methods=["POST"])
@require_edit_permission
def import_devices():
    upload = request.files.get("import_file")
    if upload is None or not upload.filename:
        flash("请选择要导入的 CSV 文件。", "error")
        return redirect(url_for("devices_page"))

    original_name = upload.filename or ""
    if Path(original_name).suffix.lower() != ".csv":
        flash("当前仅支持 CSV 导入。", "error")
        return redirect(url_for("devices_page"))

    text_stream = io.StringIO(upload.stream.read().decode("utf-8-sig"))
    reader = csv.DictReader(text_stream)
    required_columns = {"device_name"}
    if not required_columns.issubset(set(reader.fieldnames or [])):
        flash("CSV 至少需要 device_name 列。", "error")
        return redirect(url_for("devices_page"))

    imported = 0
    database = get_db()
    for row in reader:
        device_name = normalize_text(row.get("device_name"))
        if not device_name:
            continue

        device_data = {
            "device_code": normalize_text(row.get("device_code") or row.get("编号") or row.get("id_code")),
            "device_name": device_name,
            "voltage": normalize_text(row.get("voltage")),
            "current": normalize_text(row.get("current")),
            "quantity_normal": normalize_text(row.get("quantity_normal") or row.get("quantity")),
            "quantity_broken": normalize_text(row.get("quantity_broken")),
            "device_status": normalize_status(row.get("device_status") or row.get("status")),
            "remarks": normalize_text(row.get("remarks")),
            "purchase_link": normalize_text(row.get("purchase_link")),
        }
        created_at = datetime.now().isoformat(timespec="seconds")
        placeholder_slug = slugify(device_name)
        cursor = database.execute(
            """
            INSERT INTO devices (
                device_code,
                device_name,
                voltage,
                current,
                quantity,
                quantity_normal,
                quantity_broken,
                broken_details,
                device_status,
                remarks,
                purchase_link,
                folder_name,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                device_data["device_code"],
                device_data["device_name"],
                device_data["voltage"],
                device_data["current"],
                device_data["quantity_normal"],
                device_data["quantity_normal"],
                device_data["quantity_broken"],
                "[]",
                device_data["device_status"],
                device_data["remarks"],
                device_data["purchase_link"],
                f"pending-{placeholder_slug}",
                created_at,
            ),
        )
        device_id = cursor.lastrowid
        folder_name = f"device_{device_id}_{placeholder_slug}"
        device_dir = device_storage_dir(folder_name)
        device_dir.mkdir(parents=True, exist_ok=True)
        (device_dir / "images").mkdir(exist_ok=True)
        (device_dir / "attachments").mkdir(exist_ok=True)
        database.execute("UPDATE devices SET folder_name = ? WHERE id = ?", (folder_name, device_id))
        with (device_dir / "metadata.json").open("w", encoding="utf-8") as metadata_file:
            json.dump({"id": device_id, **device_data, "folder_name": folder_name, "created_at": created_at}, metadata_file, ensure_ascii=False, indent=2)
        imported += 1

    database.commit()
    flash(f"已导入 {imported} 条设备记录。", "success")
    return redirect(url_for("devices_page"))


@app.route("/device-file/<int:file_id>")
def device_file(file_id: int):
    database = get_db()
    file_row = database.execute(
        "SELECT device_id, original_name, relative_path FROM device_files WHERE id = ?",
        (file_id,),
    ).fetchone()
    if file_row is None:
        abort(404)

    relative_path = (BASE_DIR / Path(file_row["relative_path"])).resolve()
    if not relative_path.is_relative_to(BASE_DIR.resolve()):
        abort(400)

    return send_file(relative_path, conditional=True)


@app.route("/download/<int:file_id>")
def download_file(file_id: int):
    database = get_db()
    file_row = database.execute(
        "SELECT relative_path, original_name FROM device_files WHERE id = ?",
        (file_id,),
    ).fetchone()
    if file_row is None:
        abort(404)

    relative_path = (BASE_DIR / Path(file_row["relative_path"])).resolve()
    if not relative_path.is_relative_to(BASE_DIR.resolve()):
        abort(400)

    return send_file(relative_path, as_attachment=True, download_name=file_row["original_name"], conditional=True)


@app.route("/delete/<int:device_id>", methods=["POST"])
@require_edit_permission
def delete_device(device_id: int):
    database = get_db()
    device_row = database.execute(
        "SELECT folder_name, device_name FROM devices WHERE id = ?",
        (device_id,),
    ).fetchone()
    if device_row is None:
        flash("设备不存在。", "error")
        return redirect(url_for("devices_page"))

    device_dir = DEVICES_DIR / device_row["folder_name"]
    database.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    database.commit()

    shutil.rmtree(device_dir, ignore_errors=True)

    flash(f"设备 {device_row['device_name']} 已删除。", "success")
    return redirect(url_for("devices_page"))


@app.route("/categories/create", methods=["POST"])
@require_edit_permission
def create_category():
    # 支持在表单中同时提供新建名称（group_name）或从下拉选择已有目录（existing_group）
    raw_name = request.form.get("group_name") or request.form.get("existing_group")
    group_name = normalize_group_name(raw_name)
    device_ids = [int(value) for value in request.form.getlist("device_ids") if str(value).isdigit()]

    database = get_db()
    existing_group = database.execute(
        "SELECT id, folder_name FROM device_groups WHERE group_name = ?", 
        (group_name,)
    ).fetchone()

    if existing_group:
        group_id = existing_group["id"]
        folder_name = existing_group["folder_name"]
        group_dir = categories_storage_dir() / folder_name
        created_at = datetime.now().isoformat(timespec="seconds")
    else:
        created_at = datetime.now().isoformat(timespec="seconds")
        placeholder_slug = slugify(group_name)
        cursor = database.execute(
            "INSERT INTO device_groups (group_name, folder_name, created_at) VALUES (?, ?, ?)",
            (group_name, f"pending-{placeholder_slug}", created_at),
        )
        group_id = cursor.lastrowid
        folder_name = f"group_{group_id}_{placeholder_slug}"
        group_dir = categories_storage_dir() / folder_name
        group_dir.mkdir(parents=True, exist_ok=True)
        database.execute("UPDATE device_groups SET folder_name = ? WHERE id = ?", (folder_name, group_id))

    for device_id in device_ids:
        exists = database.execute("SELECT 1 FROM devices WHERE id = ?", (device_id,)).fetchone()
        if exists is None:
            continue
        database.execute(
            "INSERT OR IGNORE INTO device_group_devices (group_id, device_id) VALUES (?, ?)",
            (group_id, device_id),
        )

    # Re-fetch all device ids for this group to update metadata
    all_device_ids_in_group = [
        row[0] for row in database.execute(
            "SELECT device_id FROM device_group_devices WHERE group_id = ?",
            (group_id,)
        ).fetchall()
    ]

    with (group_dir / "metadata.json").open("w", encoding="utf-8") as metadata_file:
        json.dump(
            {
                "id": group_id,
                "group_name": group_name,
                "folder_name": folder_name,
                "device_ids": all_device_ids_in_group,
                "created_at": created_at,
            },
            metadata_file,
            ensure_ascii=False,
            indent=2,
        )

    database.commit()
    flash(f"已将选定的设备归入 {group_name} 目录。", "success")
    return redirect(url_for("categories_page"))


@app.route("/categories/<int:category_id>/rename", methods=["POST"])
@require_edit_permission
def rename_category(category_id: int):
    new_group_name = normalize_group_name(request.form.get("group_name"))
    database = get_db()
    category_row = database.execute(
        "SELECT * FROM device_groups WHERE id = ?",
        (category_id,),
    ).fetchone()
    if category_row is None:
        flash("分类目录不存在。", "error")
        return redirect(url_for("categories_page"))

    old_folder_name = category_row["folder_name"]
    new_folder_name = f"group_{category_id}_{slugify(new_group_name)}"
    database.execute(
        "UPDATE device_groups SET group_name = ?, folder_name = ? WHERE id = ?",
        (new_group_name, new_folder_name, category_id),
    )
    database.commit()

    old_dir = category_storage_dir(old_folder_name)
    new_dir = category_storage_dir(new_folder_name)
    if old_dir.exists() and old_dir != new_dir:
        if new_dir.exists():
            shutil.rmtree(new_dir, ignore_errors=True)
        old_dir.rename(new_dir)

    updated_row = database.execute(
        "SELECT * FROM device_groups WHERE id = ?",
        (category_id,),
    ).fetchone()
    if updated_row is not None:
        write_category_metadata(updated_row)

    flash(f"分类目录已重命名为 {new_group_name}。", "success")
    return redirect(url_for("categories_page"))


@app.route("/categories/<int:category_id>/delete", methods=["POST"])
@require_edit_permission
def delete_category(category_id: int):
    database = get_db()
    category_row = database.execute(
        "SELECT * FROM device_groups WHERE id = ?",
        (category_id,),
    ).fetchone()
    if category_row is None:
        flash("分类目录不存在。", "error")
        return redirect(url_for("categories_page"))

    category_dir = category_storage_dir(category_row["folder_name"])
    database.execute("DELETE FROM device_groups WHERE id = ?", (category_id,))
    database.commit()
    shutil.rmtree(category_dir, ignore_errors=True)

    flash(f"分类目录 {category_row['group_name']} 已删除。", "success")
    return redirect(url_for("categories_page"))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run Lab Equipment Manager")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Host to bind the server to")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)), help="Port to bind the server to")
    parser.add_argument("--debug", action="store_true", help="Enable Flask debug mode")
    args = parser.parse_args()

    init_db()
    app.run(host=args.host, port=args.port, debug=args.debug)
