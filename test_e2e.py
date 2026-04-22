import re
import requests

BASE = 'http://127.0.0.1:5000'

s = requests.Session()

# Add device
print('Adding device...')
add_data = {
    'device_code': 'E2E-001',
    'device_name': 'E2E Test Device',
    'voltage': '5V',
    'current': '1A',
    'quantity_normal': '1',
    'quantity_broken': '0',
    'remarks': '自动化测试创建',
    'purchase_link': '',
    'device_status': '拟采购'
}
r = s.post(BASE + '/add', data=add_data)
print('/add ->', r.status_code)

# Find newest device id from /devices
r = s.get(BASE + '/devices')
print('/devices ->', r.status_code)
html = r.text
m = re.search(r'data-search="(\d+) ', html)
if not m:
    print('无法从 /devices 页面找到设备 id')
    exit(1)
new_id = m.group(1)
print('New device id:', new_id)

# Edit device
print('Editing device name...')
edit_data = {
    'device_code': 'E2E-001',
    'device_name': 'E2E Test Device - Edited',
    'voltage': '5V',
    'current': '1A',
    'quantity_normal': '2',
    'quantity_broken': '0',
    'remarks': '自动化测试修改',
    'purchase_link': '',
    'device_status': '已采购，未入库',
    'page': '1'
}
r = s.post(f'{BASE}/edit/{new_id}', data=edit_data)
print('/edit ->', r.status_code)

# Verify edit by fetching device detail page
r = s.get(f'{BASE}/device/{new_id}')
if 'E2E Test Device - Edited' in r.text:
    print('Edit verified')
else:
    print('Edit not reflected')

# Delete device
print('Deleting device...')
r = s.post(f'{BASE}/delete/{new_id}')
print('/delete ->', r.status_code)

# Verify deletion
r = s.get(BASE + '/devices')
if f'sys: {new_id}' not in r.text:
    print('Deletion verified')
else:
    print('Deletion may have failed')
