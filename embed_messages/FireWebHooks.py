from dotenv import load_dotenv
import os
load_dotenv()
import requests
import json
from icecream import ic
from typing import Union, Optional, cast, Any, Callable, Type, List, Dict # type: ignore
from DiscordHome import PL_HOME_RULES_AND_WELCOME
from DiscordHowToPlay import PL_BFME2_DOWNLOAD, PL_BFME2_MULTIPLAYER

class SECRETS:
    BFME2_DOWNLOAD_HOOK = os.environ["BFME2_DOWNLOAD_HOOK"]
    BFME2_ONLINE_HOOK = os.environ["BFME2_ONLINE_HOOK"]
    DISCORD_RULES_HOOK = os.environ["DISCORD_RULES_HOOK"]



def SendDiscordWebhook(payload: Dict[str, Any], webhook_url: str) -> bool:
	"""
	Sends a JSON payload to the given Discord webhook URL.
	
	Args:
		payload (Dict[str, Any]): The JSON-compatible dictionary to send.
		webhook_url (str): The Discord webhook URL.

	Returns:
		bool: True if the request was successful (status code 2xx), False otherwise.
	"""
	input("Confirmar envio de webhook a discord?: ")
	
	headers = {
		"Content-Type": "application/json"
	}

	try:
		response = requests.post(webhook_url, headers=headers, data=json.dumps(payload))
		if 200 <= response.status_code < 300:
			ic("Webhook sent successfully.")
			return True
		else:
			ic(f"Failed to send webhook: {response.status_code} {response.text}")
			return False
	except requests.exceptions.RequestException as e:
		ic(f"Exception while sending webhook: {e}")
		return False





if __name__ == "__main__":
	# SendDiscordWebhook(payload = BFME2_DOWNLOAD_PAYLOAD, webhook_url=SECRETS.BFME2_DOWNLOAD_HOOK)
	SendDiscordWebhook(payload = PL_BFME2_MULTIPLAYER, webhook_url=SECRETS.BFME2_ONLINE_HOOK)
	
	
	# SendDiscordWebhook(payload = PL_HOME_RULES_AND_WELCOME, webhook_url=SECRETS.DISCORD_RULES_HOOK)
	
	