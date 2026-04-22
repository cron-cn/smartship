import re
import requests

def main():
	s = requests.Session()
	BASE = 'http://127.0.0.1:5000'
	# editing is enabled by default; no unlock required
	# fetch edit-devices
	r = s.get(BASE + '/edit-devices')
	html = r.text
	ids = re.findall(r'data-id="(\d+)"', html)
	print('ids in edit-devices:', ids)
	# fetch devices list
	r = s.get(BASE + '/devices')
	html = r.text
	ids2 = re.findall(r'data-id="(\d+)"', html)
	print('ids in /devices:', ids2)

if __name__ == '__main__':
	main()
