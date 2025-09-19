from dataclasses import dataclass
from pathlib import Path
from icecream import ic
import json
# from shlex import split
from functools import cached_property
from datetime import datetime, timezone
import requests
import sys
import time
from dotenv import load_dotenv
from typing import Protocol, Union, Optional, cast, Any, Callable, Type, List, Dict # type: ignore
import os
load_dotenv()
class SECRETS:
    PIG_WEB_HOOK = os.environ["PIG_WEB_HOOK"]
    TOKEN = os.environ["TOKEN"]

	
	
# //--------------------------------------------------------------------//
# ;;---------------------ok. funciones.input--------------------------;;
# //--------------------------------------------------------------------//

class IntegrityChecker:
	@staticmethod 
	def checkNoGamesChall(event: "ChallengeEvent"):
		"NoScoreChallenge - don't log me with games"
		if event.games_total:
			raise Exception(f"Error en el csv. Los jugadores deben tener 0 wins en un challenge tipo {event.version}.")
	@staticmethod 
	def checkNormalChall(event: "ChallengeEvent"):
		"NormalChallenge - don't log me numbers"
		if not event.games_total:
			raise Exception(f"Error en el csv. Los jugadores deben tener juegos en un challenge tipo {event.version}.")
		if event.winner.wins <= event.loser.wins:
			raise Exception(f"Error de integridad: Como es posible que el ganador no tenga mas victorias que el perdedor?")

class ChallengeReportHeading:
	@staticmethod 
	def BaseChallengeHeader(event: "ChallengeEvent") -> str:
		# Comportamiento normal
		return (
			f"\n\n{event.challenger.history.name} ({event.challenger.rank_ordinal}) has challenged "
			f"{event.defender.history.name} ({event.defender.rank_ordinal}) for his spot."
		)
		
	@classmethod 
	def EnrichedChallengeHeader(cls, event: "ChallengeEvent") -> str:
		# Comportamiento normal + traditional chlng reference
		string = cls.BaseChallengeHeader(event)
		if event.games2v2:
			string += "\nMode: Traditional challenge (4 games as 2vs2, 4 games as 1vs1, untie with 1vs1)."
		return string
		
		
	@staticmethod 
	def NoChallengeHeader(event: "ChallengeEvent") -> str:
		# in KickAddChallenge noone challenged anyone
		return ""
		
		
class PlayerHistoryImpacter:
	@staticmethod 
	def impactNormalChall(event: "ChallengeEvent"):
		"NormalChallenge is the only one that impacts historial"
		event.winner.history.append_cha(event)
		event.loser.history.append_cha(event)
		event.winner.history.append_cha_win_lose(event.winner)
		event.loser.history.append_cha_win_lose(event.loser)
			
	@staticmethod 
	def impactNoGamesChall(event: "ChallengeEvent"):
		event.winner.history.append_cha(event)
		event.loser.history.append_cha(event)
			
class Top10Impacter:
	@staticmethod 
	def impactTop10Normal(event: "ChallengeEvent"):
		"NormalChallenge - winner_takes_over"
		if event.challenger is event.winner:
			# if not isinstance(event, (NormalChallenge, NoScoreChallenge)):
			# 	raise Exception(f"Wtf class? {type(event)}")
			BaseDeDatos.top10list.remove(event.winner.history) 
			BaseDeDatos.top10list.insert(event.loser.history.get_rank(), event.winner.history) 

	@staticmethod 
	def impactTop10Challengeless(event: "ChallengeEvent"):
		"KickAddChallenge - unique method"
		# if not isinstance(event, KickAddChallenge):
		# 	raise Exception(f"Wtf class? {type(event)}")
		BaseDeDatos.top10list.remove(event.loser.history)
		BaseDeDatos.top10list.remove(event.winner.history)
		BaseDeDatos.top10list.insert(ChaSys.TOP_OF, event.loser.history)
		BaseDeDatos.top10list.insert(ChaSys.TOP_OF, event.winner.history)

@dataclass
class ChallengeBehavior:
    check_integrity: Callable
    impact_players: Callable
    impact_top10: Callable
    get_report: Callable
    get_embed: Callable
    post_to_discord: Callable
    report_header: Callable
	
class EmbedBuilders:
	@classmethod 
	def __base_embed(cls: Type["EmbedBuilders"], event: "ChallengeEvent") -> Dict[str, Any]:
		return {
			"color": event.embed_color,
			"title": "A new Challenge has been registered!",
			"description": (
				"```diff\n"
				f"- Challenge № {event.id}\n"
				f"- Update {event.fecha}\n"
				"```"
			),
			"timestamp": datetime.now(timezone.utc).isoformat(),
			"footer": {"text": "Let the challenges continue!"},
		}
		
		
	@classmethod 
	def GetNoScoreChallengeEmbed(cls: Type["EmbedBuilders"], event: "ChallengeEvent") -> Dict[str, Any]:
		#NoScoreChallenge behavior
		return cls.__base_embed(event) | {
			"fields": [{
					"name": "Players",
					"value": (
						f"- Challenger: **{event.challenger.history.name} ({event.challenger.rank_ordinal})**"
						f"\n- Defender: **{event.defender.history.name} ({event.defender.rank_ordinal})**"
					),
					"inline": False
				},{
					"name": "Outcome",
					"value": (
						f"- **{event.defender.history.name}** has refused to defend his spot or hasn't arranged a play-date to defend it.\n"
						"```diff\n"
						f"+ {event.challenger.history.name} has taken over the {event.defender.rank_ordinal} spot!\n"
						"```"
					),
					"inline": False
				},{
					"name": "Scores",
					"value": "- No wins or losses have been scored.",
					"inline": False
				},{
					"name": "Let the Challenges Continue!",
					"value": f"```diff\n{event.top10string}```",
					"inline": False
				}],
		}
		
	@classmethod
	def GetKickAddChallengeEmbed(cls: Type["EmbedBuilders"], event: "ChallengeEvent") -> Dict[str, Any]:
		#KickAddChallenge behavior
		return cls.__base_embed(event) | {
			"fields": [{
					"name": "Kick-Add Update",
					"value": (
						f"- Since Challenge {event.defender.previous_challenge.id}, {event.defender.history.name} has not played any game or challenge in {event.defender.days_since_last_chall} days."
					),
					"inline": False
				},{
					"name": "Outcome",
					"value": (
						"```diff\n"
						f"- {event.defender.history.name} ({event.defender.rank_ordinal}) has been kicked from the list.\n"
						f"+ {event.challenger.history.name} has been set to in the 10th spot.\n"
						"```"
					),
					"inline": False
				},{
					"name": "Scores",
					"value": "- No wins or losses have been scored.",
					"inline": False
				},{
					"name": "Let the Challenges Continue!",
					"value": f"```diff\n{event.top10string}```",
					"inline": False
				}
			],
		}
		
	@classmethod 
	def GetNormalChallengeEmbed(cls: Type["EmbedBuilders"], event: "ChallengeEvent") -> Dict[str, Any]:
		#NormalChallenge behavior
		score = f"- **Score 1vs1**: {event.winner.wins1v1}-{event.loser.wins1v1} for **{event.winner.history.name}**"
		if event.games2v2:
			score += (
				f"\n- **Score 2vs2**: {event.winner.wins2v2}-{event.loser.wins2v2} for **{event.winner.history.name}**"
				f"\n- **Total Score**: {event.winner.wins}-{event.loser.wins} for **{event.winner.history.name}**"
			)
		embed: Dict[str, Any] = cls.__base_embed(event) | {
			"fields": [{
					"name": "Players",
					"value": (
						f"- Challenger: **{event.challenger.history.name} ({event.challenger.rank_ordinal})**"
						f"\n- Defender: **{event.defender.history.name} ({event.defender.rank_ordinal})**"
					),
					"inline": False
				},{
					"name": "Scores",
					"value": score,
					"inline": False
				},{
					"name": "Outcome",
					"value": (
						"```diff\n"
						f"+ {event.winner.history.name} {'flawlessly ' if event.loser.wins == 0 else ''}{'defended' if event.defender is event.winner else 'has taken over'} the {event.defender.rank_ordinal} spot!\n"
						"```"
					),
					"inline": False
				},{
					"name": "Games Played In",
					"value": f"{event.version}",
					"inline": True
				},{
					"name": "Let the Challenges Continue!",
					"value": f"```diff\n{event.top10string}```",
					"inline": False
				}
			],
		}
		if event.notes:
			embed["fields"].insert(-2,{
				"name": "Comments: ",
				"value": f"*- {event.notes}*",
				"inline": False
			})
		return embed
				
			
class DiscordPoster:
	@staticmethod 
	def NormalChallengePoster(event: "ChallengeEvent", discord_message:str) -> requests.Response:
		print("NormalChallenge doing a NormalChallengePoster") 
		response = requests.post(
			ChaSys.webhook_url,
			data={"content": discord_message},
			files={"file": open(event.replays_dir, "rb")}
		)
		# print(response.status_code)
		if response.status_code != 200:
			return response
			
		webhook_message = response.json()
		# print(webhook_message)
		message_id = webhook_message["id"]
		webhook_url_edit = f"{ChaSys.webhook_url}/messages/{message_id}"
		# print(webhook_url_edit)
		edit_payload: dict[str, Any] = {
			"content": discord_message,
			"embeds": [event.embed]
		}
		# print(edit_payload)
		return requests.patch(
			webhook_url_edit,
			json=edit_payload
		)
				
	@staticmethod 
	def KickAddChallengePoster(event: "ChallengeEvent", discord_message:str) -> requests.Response:
		print("KickAddChallenge doing a KickAddChallengePoster") 
		if event.notes:
			event.embed["fields"].insert(-2,{
				"name": "Comments: ",
				"value": f"*- {event.notes}*",
				"inline": False
			})
		payload:dict[str, Any] = {
			"content": discord_message,
			"embeds": [event.embed]
		}
		return requests.post(ChaSys.webhook_url, json=payload)
		
				
	@staticmethod 
	def NoScoreChallengePoster(event: "ChallengeEvent", discord_message:str) -> requests.Response:
		print("NoScoreChallenge doing a NoScoreChallengePoster") 
		if event.notes:
			event.embed["fields"].insert(-2,{
				"name": "Comments: ",
				"value": f"*- {event.notes}*",
				"inline": False
			})
		payload: dict[str, Any] = {
			"content": discord_message,
			"embeds": [event.embed]
		}
		return requests.post(ChaSys.webhook_url, json=payload)
				
		
		
class HtmlColors:
	ORANGEISH:int = 0xFFA500
	PURPLEISH:int = 0x981D98
	BLUEISH:int = 0x5DD9DF

class ReportBuilder:
	@staticmethod 
	def GetKickAddReport(event: "ChallengeEvent") -> str:
		# KickAddChallenge behavior
		commment_line = f"\n\n\tComment: {event.notes}" if event.notes else ""
		return (
			f"{event.behavior.report_header(event)}"
			f"\n\nAddAndKickUpdate: "
			f"Since Challenge {event.defender.previous_challenge.id}, {event.defender.history.name} has not played any game or challenge in {event.defender.days_since_last_chall} days."
			f"\n\n- {event.defender.history.name} has been kicked from the {event.defender.rank_ordinal} spot and from the list."
			f"\n\n+ {event.challenger.history.name} has been added to the top10 list, starting in the 10th spot."
			f"{commment_line}"
			f"\n\nNo wins or losses have been scored."
		)
		
	@staticmethod 
	def GetNoScoreReport(event: "ChallengeEvent") -> str:
		# NoScoreChallenge behavior
		commment_line = f"\n\n\tComment: {event.notes}" if event.notes else ""
		return (
			f"{event.behavior.report_header(event)}"
			f"\n\nSpotUndefended: {event.defender.history.name} has refused to defend his spot or hasn't arranged a play-date to defend it."
			f"\n\n+ {event.challenger.history.name} has taken over the {event.defender.rank_ordinal} spot!"
			f"{commment_line}"
			f"\n\nNo wins or losses have been scored."
		)

	@staticmethod 
	def GetNormalChallengeReport(event: "ChallengeEvent") -> str:
		# NormalChallenge behavior
		def __report_01_report_defenseortakeover():
			flawlessly = "flawlessly " if event.loser.wins == 0 else ""
			if event.defender is event.winner:
				return f"\n\n+ {event.defender.history.name} has {flawlessly}defended the {event.defender.rank_ordinal} spot!"
			else:
				return f"\n\n+ {event.challenger.history.name} has {flawlessly}taken over the {event.defender.rank_ordinal} spot!"
				
		def __report_01_report_score():
			string = f"\nScore 1vs1: {event.winner.wins1v1}-{event.loser.wins1v1} for {event.winner.history.name}"
			if event.games2v2:
				string += (f"\nScore 2vs2: {event.winner.wins2v2}-{event.loser.wins2v2} for {event.winner.history.name}"
					f"\nScore: {event.winner.wins}-{event.loser.wins} for {event.winner.history.name}"
				)
			return string
			
		commment_line = f"\n\n\tComment: {event.notes}" if event.notes else ""
		return (
			f"{event.behavior.report_header(event)}"
			f"{__report_01_report_score()}"
			f"{__report_01_report_defenseortakeover()}"
			f"{commment_line}"
			f"\n\nGames were played in {event.version}"
		)


# //--------------------------------------------------------------------//
# ;;---------------------ok. funciones.input--------------------------;;
# //--------------------------------------------------------------------//

		
		
		
def wait_minutes(minutes:int) -> None:
	towait = minutes*60
	print(f"Waiting {minutes} minutes...")
	time.sleep(towait)
		

def get_int(msg:str , indent: int=0, show_error: bool=True, min:Optional[int]=None, max:Optional[int]=None) -> int:
	tab = '\t'
	while True:
		if min and max:
			ingreso = input(f"{tab*indent}{msg} (Min:{min},Max:{max}): ")
		elif min:
			ingreso = input(f"{tab*indent}{msg} (Min:{min}): ")
		elif max:
			ingreso = input(f"{tab*indent}{msg} (Max:{max}): ")
		else:
			ingreso = input(f"{tab*indent}{msg}")
		try: 
			num = int(ingreso)
			if (min is None or num >= min) and (max is None or num <= max):
				return num
			else:
				print(f"{tab*(indent+1)}Error de ingreso: '{ingreso}' esta fuera del rango {min}-{max}.")
		except ValueError:
			if show_error:
				print(f"{tab*(indent+1)}Error de ingreso: '{ingreso}' no es un numero.")

def get_boolean(msg:str, letra1:str="Y", letra2:str="N", indent:int=0) -> bool:	
	while True:
		tab = '\t'
		ingreso = input(f"{tab*indent}{msg} Ingrese {letra1}/{letra2}: ").upper()
		if ingreso == letra1:
			return True
		elif ingreso == letra2:
			return False
	
	
	
	
	
	
	
	
	
#-------------------------------------------------------------------------------------------------------------#
#"""-------------------------------------------PlayerHistory.Class.01---------------------------------------------"""#
#-------------------------------------------------------------------------------------------------------------#
class PlayerHistory:
	challenges: list["ChallengeEvent"]
	def __init__(self, key:str, value:dict[str,list[str]]):
		self.key:str = key
		self.names = value["nicknames"]
		# self.discord_id = value["discord_id"]
		self.cha_wins = 0
		self.cha_loses = 0
		self.challenges = []
		self.wins_total = 0
		self.wins1v1_total = 0
		self.wins2v2_total = 0
		self.games_played_total = 0
		self.games_played_1v1 = 0
		self.games_played_2v2 = 0
		
	###----------------PlayerHistory.Public.Methods------------###
	
	
	def last_active_challenge(self:"PlayerHistory") -> int|None:
		today = datetime.today()
		for challenge in reversed(self.challenges):
			if challenge.has_replays:
				return (challenge.date - today).days
		return None
	
	
	
	def append_cha(self:"PlayerHistory", challenge:"ChallengeEvent") -> None:
		self.challenges.append(challenge)
		self.games_played_total += challenge.games_total
		self.games_played_1v1 += challenge.games1v1
		self.games_played_2v2 += challenge.games2v2
		
	def append_cha_win_lose(self:"PlayerHistory", player_in_chall:"PlayerInChallenge") -> None:
		self.wins_total += player_in_chall.wins
		self.wins1v1_total += player_in_chall.wins1v1
		self.wins2v2_total += player_in_chall.wins2v2
		if player_in_chall is player_in_chall.challenge.winner:
			self.cha_wins += 1
		else:
			self.cha_loses += 1
	
	def get_status(self) -> str:
		return f"|{self.key}|\tRank:{self.get_rank()}\t|Wins:{self.cha_wins}|Loses:{self.cha_loses}"
		
	def get_rank(self) -> int:
		return BaseDeDatos.top10list.index(self)
		
	def get_1v1_vs(self:"PlayerHistory", other:"PlayerHistory", print_em:bool=True) -> Optional[bool]:
		self_wins:set[ChallengeEvent] = {cha for cha in self.challenges if cha.winner.history == self and cha.loser.history == other}
		other_wins:set[ChallengeEvent] = {cha for cha in self.challenges if cha.winner.history == other and cha.loser.history == self}
		ic(self_wins)
		self_wins_len = len(self_wins)
		other_wins_len = len(other_wins)
		total_matches_len = self_wins_len + other_wins_len
		if total_matches_len == 0:
			winrate = 0
		else:
			winrate = (self_wins_len / total_matches_len) * 100.0
		if print_em:
			print(f"{self.name} vs {other.name}: {self_wins_len}-{other_wins_len} | WinRate: {winrate}")
		else:
			if total_matches_len > 0:
				return self_wins_len > other_wins_len 
			else:
				return None
		
	###--------------------PlayerHistory.Public.Properties----------------###
	@cached_property
	def name(self) -> str:
		return self.names[0]

	@cached_property
	def loses_total(self) -> int:
		return self.games_played_total - self.wins_total
		
	@cached_property	
	def loses_1v1_total(self) -> int:
		return self.games_played_1v1 - self.wins1v1_total
		
	@cached_property	
	def loses2v2_total(self) -> int:
		return self.games_played_2v2 - self.wins2v2_total
	
	@cached_property
	def fecha_de_alta(self) -> datetime:
		return self.challenges[0].date

	###--------------------PlayerHistory.Dunder.Methods----------------###
	def __lt__(self:"PlayerHistory", other:"PlayerHistory") -> bool:
		return self.key < other.key
		
	def __gt__(self:"PlayerHistory", other:"PlayerHistory") -> bool:
		def get_cha_winrate(player:"PlayerHistory"):
			return (player.wins1v1_total / player.games_played_total) * 100.0 if player.games_played_total != 0 else 0
			
		bol = self.get_1v1_vs(other, print_em=False)
		if bol is None:
			bol = get_cha_winrate(self) > get_cha_winrate(other)
		print(f"{self.key} better than {other.key} = {bol}")
		return bol

	def __repr__(self:"PlayerHistory") -> str:
		return f"|{self.key}|\t|Wins:{self.cha_wins}|Loses:{self.cha_loses}"










#------------------------------------------------------------------------------------------#
#"""---------------------------------ChallengeEvent.Class.02----------------------------"""#
#------------------------------------------------------------------------------------------#
@dataclass
class ChallengeEvent:
	id: int
	row: dict[str, str]
	embed_color: int
	behavior: ChallengeBehavior
	version: str
	date: datetime
	notes: str
	winner: 'PlayerInChallenge'
	has_replays: bool
	loser: 'PlayerInChallenge'
		
	###--------------------ChallengeEvent.Static.Methods-------------###
	@classmethod
	def FromRow(cls:Type["ChallengeEvent"], cha_id:int, version:str, row:dict[str, str]) -> "ChallengeEvent":
		winner = PlayerInChallenge(cha_id, row["w_key"], row["w_wins1v1"], row["w_wins2v2"])
		loser = PlayerInChallenge(cha_id, row["l_key"], row["l_wins1v1"], row["l_wins2v2"])
		date = datetime.strptime(row["date"], '%Y-%m-%d')
		
		if version == "NO_SCORE_MODE":
			return cls(
				id = cha_id, 
				row = row, 
				embed_color = HtmlColors.ORANGEISH, 
				behavior = ChallengeBehavior(
					check_integrity = IntegrityChecker.checkNoGamesChall,
					impact_players = PlayerHistoryImpacter.impactNoGamesChall,
					impact_top10 = Top10Impacter.impactTop10Normal,
					get_report = ReportBuilder.GetNoScoreReport,
					get_embed = EmbedBuilders.GetNoScoreChallengeEmbed,
					post_to_discord = DiscordPoster.NoScoreChallengePoster,
					report_header = ChallengeReportHeading.BaseChallengeHeader,
				),
				has_replays = False, 
				version = row["version"],
				date = date,
				notes = row['notes'],
				winner = winner,
				loser = loser
			)
		elif version == "KICK_ADD_MODE":
			return cls(
				id = cha_id, 
				row = row, 
				embed_color = HtmlColors.PURPLEISH, 
				behavior = ChallengeBehavior(
					check_integrity = IntegrityChecker.checkNoGamesChall,
					impact_players = PlayerHistoryImpacter.impactNoGamesChall,
					impact_top10 = Top10Impacter.impactTop10Challengeless,
					get_report = ReportBuilder.GetKickAddReport,
					get_embed = EmbedBuilders.GetKickAddChallengeEmbed,
					post_to_discord = DiscordPoster.KickAddChallengePoster,
					report_header = ChallengeReportHeading.NoChallengeHeader,
				),
				has_replays = False, 
				version = row["version"],
				date = date,
				notes = row['notes'],
				winner = winner,
				loser = loser
			)
		else:
			return cls(
				id = cha_id, 
				row = row, 
				embed_color = HtmlColors.BLUEISH,
				behavior = ChallengeBehavior(
					check_integrity = IntegrityChecker.checkNormalChall,
					impact_players = PlayerHistoryImpacter.impactNormalChall,
					impact_top10 = Top10Impacter.impactTop10Normal,
					get_report = ReportBuilder.GetNormalChallengeReport,
					get_embed = EmbedBuilders.GetNormalChallengeEmbed,
					post_to_discord = DiscordPoster.NormalChallengePoster,
					report_header = ChallengeReportHeading.EnrichedChallengeHeader,
				),
				has_replays = True, 
				version = row["version"],
				date = date,
				notes = row['notes'],
				winner = winner,
				loser = loser
			)
	
	
	###--------------------ChallengeEvent.Public.Methods-------------###
	def do_stuff(self: "ChallengeEvent") -> None:
		self.behavior.check_integrity(self)
		for player in {self.winner, self.loser}:
			ChaSys.set_top10_rank(player)
		
		self.behavior.impact_players(self)
		self.behavior.impact_top10(self)
		self.top10string = ChaSys.get_top10string()
			
	def Rename_existing_replaypack(self: "ChallengeEvent", torename:str, compress:bool) -> None:
		if self.has_replays:
			existing = ChaSys.chareps / torename
			if existing.exists() and not self.replays_dir.exists():
				existing.rename(ChaSys.chareps/self.replays_dir.name)
				print(f"* {torename} was renamed to {self.replays_dir.name}")
			# if compress:
				# ChallengeSystem.compress_folder(ideal)
		
		
	def preguntar_por_replaypack(self: "ChallengeEvent") -> None:
		while self.has_replays and not self.replays_dir.exists():
			if not get_boolean(f"Replay pack not found: << {self.replays_dir.relative_to(self.replays_dir.parent.parent)} >> \n{self.replays_dir.stem}\n\tDo you want to make sure to rename replays accordingly and try again?"):
				sys.exit("Ok bye")
				
	def as_row(self: "ChallengeEvent") -> str:
		columns = map(lambda x: str(x), [self.id, self.version, self.winner.history.key, self.winner.wins1v1, self.winner.wins2v2, self.loser.history.key, self.loser.wins1v1, self.loser.wins2v2, self.fecha, self.notes])
		return ";".join(columns)+"\n"
		
	def post(self: "ChallengeEvent", confirmed: bool, delay: int) -> None:
		if not confirmed and not get_boolean(f"\tConfirm send challenge Nº{self.id} to Chlng|Updates?"):
			return
		if delay:
			wait_minutes(delay)
		discord_message = "📢 **Challenge Update!** A new match result is in! Check out the details below."
		response = self.behavior.post_to_discord(self, discord_message)
		
		if response.status_code in {200, 204}:
			print(f"Challenge Nº{self.id} successfully sent to Discord via the webhook!")
		else:
			print(f"Failed to send webhookof challenge Nº{self.id}: \n{response.status_code} - {response.text}")

	###--------------------ChallengeEvent.Properties-------------###
	@cached_property
	def fecha(self: "ChallengeEvent") -> str:
		return self.date.strftime('%Y-%m-%d')
		
	@cached_property
	def games_total(self: "ChallengeEvent") -> int:
		return self.winner.wins + self.loser.wins
		
	@cached_property
	def games1v1(self: "ChallengeEvent") -> int:
		return self.winner.wins1v1 + self.loser.wins1v1
		
	@cached_property
	def games2v2(self: "ChallengeEvent") -> int:
		return self.winner.wins2v2 + self.loser.wins2v2
			
	@cached_property
	def challenger(self: "ChallengeEvent") -> "PlayerInChallenge":
		return self.winner if self.winner.rank > self.loser.rank else self.loser

	@cached_property
	def defender(self: "ChallengeEvent") -> "PlayerInChallenge":
		return self.winner if self.challenger is self.loser else self.loser
		
	@cached_property
	def embed(self: "ChallengeEvent") -> Dict[str, Any]:
		return self.behavior.get_embed(self)
		
	@cached_property
	def replays_dir(self: "ChallengeEvent") -> Path:
		return ChaSys.chareps / f"Challenge{self.id}_{self.challenger.history.key}_vs_{self.defender.history.key},_{self.challenger.wins}-{self.defender.wins},_{self.version}.rar"
		
	###--------------------ChallengeEvent.Dunder.Methods----------------###
		
	def __eq__(self, other: object) -> bool:
		if not isinstance(other, ChallengeEvent):
			return NotImplemented
		return self.id == other.id

	def __hash__(self: "ChallengeEvent"):
		return hash(self.id)
		
	def __lt__(self: "ChallengeEvent", other: "ChallengeEvent"):
		return self.id < other.id
		
	def __repr__(self: "ChallengeEvent"):
		return f"|Cha{self.id}|{self.version}|{self.winner}{self.winner.wins}|{self.loser}{self.loser.wins}|"
		
	def __str__(self: "ChallengeEvent"):
		return (
			"\n------------------------------------"
			f"\n{self.replays_dir.stem if self.has_replays else 'NO_GAMES_NO_REPLAYS'}"
			"\n```diff\n"
			f"\n- Challenge № {self.id}"
			f"\n- Update {self.fecha}"
			f"{self.behavior.get_report(self)}"
			f"\n\nLet the challenges continue!"
			f"\n\n{self.top10string}```"
		)
		
			
			

#-------------------------------------------------------------------------------------------------------------#
#"""---------------------------------------PlayerInChallenge.Class.03--------------------------------------"""#
#-------------------------------------------------------------------------------------------------------------#

class PlayerInChallenge:
	rank: int
	def __init__(self, challenge_id: int, key: str, wins1v1: str, wins2v2: str):
		self.key = key
		self.challenge_id = challenge_id
		self.wins1v1 = int(wins1v1)
		self.wins2v2 = int(wins2v2)
	###----------------PlayerInChallenge.Properties-------------###
	
	
	
	
	@cached_property
	def wins(self) -> int:
		return self.wins1v1 + self.wins2v2
	
	@cached_property
	def challenge(self) -> ChallengeEvent:
		return BaseDeDatos.CHALLENGES[self.challenge_id]
		
	@cached_property
	def previous_challenge(self) -> ChallengeEvent:
		return self.history.challenges[self.history.challenges.index(self.challenge)-1]
		
	@cached_property
	def days_since_last_chall(self) -> int:
		return (self.challenge.date - self.previous_challenge.date).days
		
	@cached_property
	def rank_ordinal(self) -> str:
		ordinal = { 
			0: "1st", 1: "2nd", 2: "3rd", 3: "4th", 4: "5th", 5: "6th", 6: "7th", 7: "8th", 8: "9th", 
			9: "10th",
			10: "11th",
			11: "12th",
			12: "13th",
			13: "14th",
			14: "15th",
		
		}
		return ordinal.get(self.rank, "from outside the list")
		
	@cached_property
	def history(self) -> PlayerHistory:
		return BaseDeDatos.PLAYERS[self.key]

	###--------------------PlayerInChallenge.Dunder.Methods----------------###
	def __repr__(self) -> str:
		return f"|{self.key}|"




#-------------------------------------------------------------------------------------------------------------#
#"""---------------------------------------BaseDeDatos.Class.04-----------------------------------------"""#
#-------------------------------------------------------------------------------------------------------------#
class BaseDeDatosClass:
	PLAYERS:dict[str, PlayerHistory]
	top10list:list[PlayerHistory]
	def __init__(self, players_json: Path, chacsv: Path):
		player_data: dict[str, dict[str, dict[str, list[str]]]] = json.load(open(players_json))
		self.chacsv = chacsv
		self.PLAYERS  = { key: PlayerHistory(key, value) for key, value in player_data["active_players"].items() }
		self.top10list = list(map(lambda x: self.PLAYERS[x], player_data["legacy"]["top10"]))
	
	def re_write_csv_dabase(self: "BaseDeDatosClass"):
		# if not get_boolean("Are you sure you want to re-write the .csv database? You better have a backup"):
			# return
			
		supastring = "key;version;w_key;w_wins1v1;w_wins2v2;l_key;l_wins1v1;l_wins2v2;date;notes\n"
		for cha in reversed(self.CHALLENGES):
			supastring += cha.as_row()

		with open(self.chacsv, mode='w', newline='', encoding='latin1') as file:
			file.write(supastring)
		print(".csv guardado.")
		
	###----------------ChallengeSystem.Private.Methods------------###
	@cached_property
	def CHALLENGES(self: "BaseDeDatosClass") -> list[ChallengeEvent]:
		if not self.chacsv.exists() or self.chacsv.stat().st_size == 0:
			raise Exception(f"No existe {self.chacsv}")
			
		lines = self.chacsv.read_text(encoding='latin1').splitlines()
		headers = lines[0].strip().split(';')
		rows = [line.strip().split(';') for line in lines[1:]]
		key_column = 0  # the column that says KEY
		sorted_rows = sorted(rows, key=lambda row: int(row[key_column]))

		# find max key to pre-size the list
		max_key = max(int(row[key_column]) for row in sorted_rows)
		dataaaa: list[ChallengeEvent | None] = [None] * (max_key + 1)

		for row in sorted_rows:
			row_dict = {headers[i]: row[i] for i in range(len(headers))}
			key = int(row_dict['key'])
			version = row_dict['version']
			dataaaa[key] = ChallengeEvent.FromRow(key, version, row_dict)
		return cast(list[ChallengeEvent], dataaaa)
		
		
		
class ChallengeSystem:
	TOP_OF = 9 # 14 # 20
	def __init__(self, chareps: Path, chalog: Path, status: Path, webhook_url:str) -> None:
		self.chareps = chareps
		self.chalog = chalog
		self.status = status
		self.webhook_url = webhook_url
	
	###----------------ChallengeSystem.Public.Methods------------###
	
	
	def show_most_inactive_players(self: "ChallengeSystem") -> None:
		# sorted_players = sorted(BaseDeDatos.top10list[0:10], key=lambda x: [x.last_challenge.date]) # type: ignore
		print("Most inactive players")
		for i, player, in enumerate(BaseDeDatos.top10list, start=1):
			print(f"Rank {i}: {player.name} | Inactive days: {player.last_active_challenge()}")
			
	
	
	
	
	def do_stuff(self: "ChallengeSystem") -> None:
		for challenge in BaseDeDatos.CHALLENGES:
			challenge.do_stuff()
		
	def get_top10string(self: "ChallengeSystem") -> str:
		top10string = "\t\tTOP 10\n"
		# ic(BaseDeDatos.top10list)
		for i in range(self.TOP_OF, -1, -1):	#iterar del 9 al 0
			if i >= len(BaseDeDatos.top10list):
				continue
			player = BaseDeDatos.top10list[i]
			top10string += f"\t{i+1:<4}. {player.name:20} {player.cha_wins}-{player.cha_loses}\n"
		return top10string
	
	def set_top10_rank(self: "ChallengeSystem", player:PlayerInChallenge) -> None:
		try:
			player.rank = BaseDeDatos.top10list.index(player.history)
		except ValueError:
			BaseDeDatos.top10list.append(player.history)
			player.rank = BaseDeDatos.top10list.index(player.history)
	
	def write_status(self: "ChallengeSystem") -> None:
		super_string = "\n".join(str(player.get_status()) for player in sorted( BaseDeDatos.PLAYERS.values() ))
		with open(self.status, "w", encoding='utf-8') as file:
			file.write(super_string)
			print(f"* {self.status.name} was updated")
			
	def write_embeds(self: "ChallengeSystem") -> None:
		all_instances = {cha.id: cha.embed for cha in reversed(BaseDeDatos.CHALLENGES)}
		filepath = r"output\embeds.json"
		with open(filepath, "w") as json_file:
			json.dump(all_instances, json_file, indent=4)
			
			
	def write_chalog(self: "ChallengeSystem") -> None:
		# super_string = f"##AutoGenerated by 'ChallengeSystem' {datetime.today().strftime("%Y-%m-%d")}\nRegards, Bambi\n\n"
		super_string = f"##AutoGenerated by 'ChallengeSystem'\nRegards, Bambi\n\n"
		for num, cha in enumerate( sorted( BaseDeDatos.CHALLENGES,reverse=True ) , start=1):
			if num == 1:
				cha.Rename_existing_replaypack("torename.rar", compress=False)
				print(cha)
			super_string += str(cha)
		
		with open(self.chalog, "w", encoding='utf-8') as file:
			file.write(super_string)
			print(f"* {self.chalog.name} was updated")
	
	def send_all_posts(self: "ChallengeSystem", confirmed:bool, start_with:int, finish_at: int, initial_delay: int, delay_between: int) -> None:
		if not confirmed and not get_boolean(f"Confirm do you want recursively post challenges between {start_with}-{finish_at} in {initial_delay} minutes each {delay_between} minutes"):
			return
		for chakey in range(start_with, finish_at+1):
			BaseDeDatos.CHALLENGES[chakey].preguntar_por_replaypack()	
		
		BaseDeDatos.CHALLENGES[start_with].post(confirmed=True, delay=initial_delay)
		for chakey in range(start_with+1, finish_at+1):
			BaseDeDatos.CHALLENGES[chakey].post(confirmed=True, delay=delay_between)
			
	def execute_argv_operations_if_any(self: "ChallengeSystem", argv: list[str]) -> None:
		from shlex import split

		# Rango válido de challenges
		min_chall = BaseDeDatos.CHALLENGES[0].id
		max_chall = BaseDeDatos.CHALLENGES[-1].id

		# Valores por defecto
		argv_dict: dict[str, Any] = {
			"action": "post",             # "post" o "post_all"
			"chaId": max_chall,           # Último challenge disponible
			"initDelay": 0,               # Delay antes del primer post
			"betweenDelay": 7,            # Delay entre múltiples posts (solo post_all)
			"confirmed": False,           # Confirmación manual
		}

		# Parseo de argumentos por CLI
		if len(argv) > 1:
			for arg in argv[1:]:  # Ignora el nombre del script
				if ":" in arg:
					key, value = arg.split(":", 1)
					key = key.strip().lower()

					if key in {"id", "chaid"}:
						key = "chaId"
						value = int(value)
					elif key in {"initdelay", "betweendelay"}:
						value = int(value)
					elif key == "confirmed":
						value = value.lower() in {"true", "1", "yes"}
					elif key == "action":
						value = value.lower()
						if value not in {"post", "post_all"}:
							raise ValueError(f"Acción inválida: {value}")
					argv_dict[key] = value
		else:
			# Modo interactivo si no se pasan argumentos
			argv_dict["chaId"] = get_int("Insertar challenge id: ", min=min_chall, max=max_chall)
			argv_dict["action"] = "post_all" if argv_dict["chaId"] < max_chall and get_boolean("¿Postear todos desde este ID? ") else "post"
			argv_dict["initDelay"] = get_int("Delay inicial (minutos): ", min=0)
			argv_dict["confirmed"] = False  # Confirmación interactiva no requerida en este modo

		# Validaciones
		if not (min_chall <= argv_dict["chaId"] <= max_chall):
			raise ValueError(f"Challenge ID inválido: {argv_dict['chaId']}. Rango válido: {min_chall}-{max_chall}")

		# Ejecución
		if argv_dict["action"] == "post":
			instance = BaseDeDatos.CHALLENGES[argv_dict["chaId"]]
			instance.preguntar_por_replaypack()
			instance.post(
				confirmed=argv_dict["confirmed"],
				delay=argv_dict["initDelay"],
			)

		elif argv_dict["action"] == "post_all":
			self.send_all_posts(
				confirmed=argv_dict["confirmed"],
				start_with=argv_dict["chaId"],
				finish_at=max_chall,
				initial_delay=argv_dict["initDelay"],
				delay_between=argv_dict["betweenDelay"],
			)

		else:
			raise ValueError(f"Acción desconocida: {argv_dict['action']}")


	def get_challenge(self: "ChallengeSystem", hint: Optional[int]) -> ChallengeEvent:
		min=1
		max=len(BaseDeDatos.CHALLENGES)
		if hint is None:
			return BaseDeDatos.CHALLENGES[get_int(f"Select challenge. Type the ID (min: {min}, max:{max}): ", indent=0, min=min, max=max)]
		elif result := BaseDeDatos.CHALLENGES[hint]:
			return result
		else:
			raise Exception(f"Challenge of id {hint} not found. Logged challenges are between {min} and {max}.")

	def consult_03_player_vs_player(self:"ChallengeSystem", p1_key:str, p2_key:str, print_em:bool) -> Optional[bool]:
		return BaseDeDatos.PLAYERS[p1_key].get_1v1_vs(BaseDeDatos.PLAYERS[p2_key], print_em=print_em)
		
	###----------------ChallengeSystem.Static.Methods------------###
	# @staticmethod
	# def compress_folder(folder_path):
		# if folder_path.exists():
			# if not folder_path.is_dir():
				# raise ValueError("Input path must be a directory.")
			# archive_path = folder_path.with_suffix(".7z")
			# with py7zr.SevenZipFile(archive_path, 'w') as archive:
				# archive.writeall(folder_path)
			# print(f"* {folder_path.name} was 7ziped")
			
			
		
		
		
		
		
#-------------------------------------------------------------------------------------------------------------#
#"""---------------------------------------------ok.Iniciar-------------------------------------------------"""#
#-------------------------------------------------------------------------------------------------------------#
if __name__ == "__main__":
	BaseDeDatos = BaseDeDatosClass(
		players_json = Path.cwd() / "data" / "players.json",
		chacsv = Path(r"data/challenges.csv"),
	)
	ChaSys = ChallengeSystem(
		chareps = Path(r"replays"),
		chalog = Path(r"output/challenges.log"),
		status = Path(r"output/status.log"),
		webhook_url = SECRETS.PIG_WEB_HOOK,
	)
	ChaSys.do_stuff()
	
	
	# SendDiscordWebhook(payload = BFME2_PAYLOAD_1, webhook_url=BFME2_DOWNLOAD_HOOK)
	# SendDiscordWebhook(payload = BFME2_PAYLOAD_2, webhook_url=BFME2_ONLINE_HOOK)
	
	
	
	ChaSys.write_chalog();
	ChaSys.write_status();
	ChaSys.show_most_inactive_players();
	
	# ChaSys.write_embeds();
	# BaseDeDatos.re_write_csv_dabase();
	
	
		
	"""1. Consultas functions"""
	# ChaSys.consult_03_player_vs_player("ECTH", "ANDY", print_em=True)
	# ChaSys.consult_03_player_vs_player("ECTH", "ASTRO", print_em=True)
	# ChaSys.consult_03_player_vs_player("ECTH", "AHWE", print_em=True)
	# ChaSys.consult_03_player_vs_player("ECTH", "YUSUF", print_em=True)
	# ChaSys.consult_03_player_vs_player("ECTH", "ENUMA", print_em=True)
	# ChaSys.consult_03_player_vs_player("ECTH", "GANNICUS", print_em=True)
	
	
	
	# ChaSys.consult_03_player_vs_player("OTTO", "ANDY", print_em=True)
	# ChaSys.consult_03_player_vs_player("OTTO", "AHWE", print_em=True)
	# ChaSys.consult_03_player_vs_player("OTTO", "ECTH", print_em=True)
	
	
	# ChaSys.consult_03_player_vs_player("OTTO", "ASTRO", print_em=True)
	# ChaSys.consult_05_2v2_score()
	
	"""2. Argv"""
		# python cha.py 312
		# python cha.py 314 post
		# python cha.py 314 post_till_end
	ChaSys.execute_argv_operations_if_any(sys.argv);
	
	"""3. SendToChlngUpdates"""
	# ChaSys.get_challenge(hint=None).post(confirmed=false, delay=0)


