import requests
import base64
import uuid

client_id = "019c9dd5-08ad-714c-8358-5945e8c15fee"
client_secret = "90a0e997-4015-458f-907a-d59f5d9e68a7"

auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
rq_uid = str(uuid.uuid4())

url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
headers = {
    'Content-Type': 'application/x-www-form-urlencoded',
    'Accept': 'application/json',
    'RqUID': rq_uid,
    'Authorization': f'Basic {auth}'
}
data = {'scope': 'GIGACHAT_API_PERS'}

response = requests.post(url, headers=headers, data=data, verify=False)
print(f"RqUID: {rq_uid}")
print(f"Статус: {response.status_code}")
print(f"Ответ: {response.text}")