# ChallengeSystem & BambiBot

data/challenges.csv

types of challenge: 
normal: used by a challenges fully completed, should be posted with the replay pack. when adding the row in the .csv, the order of the players dont matter. cha.py will figure out the roles of p1/p2 automatically. in the version label should be the patch name.
KICK_ADD_MODE: used when we want to delete a player from the list, pushing up everyone behind. but in the 10th spot we add a new player. added player must be loged as p1 and kickes as p2. must to write this kickandmode flag in the version column. 1v1/2v2 columns must be zero.
NO_SCORE_MODE: used when one player challenges another but he's dodged, or he's inactive, or refuses to defend his own spot. he simply loses the spot but we dont alter the winrates of any player. 1v1/2v2 columns must be cero. patch column must to be this flag. p1 must be the challenger and p2 must be the defender.



once .csv is updated, run cha.py to autoupdate the data/cha.log, which has the story of challenges. in the top of the file there will be the latest.


## 📘 CLI Documentation for `cha.py`

### 🧩 Structure
```bash
python cha.py [action:<post|post_all>] [id:<int>] [betweenDelay:<int>] [initDelay:<int>] [confirmed:<true|false>]
```

### 🛠️ Optional Arguments

| Argument        | Description                                                                                   | Default      |
|----------------|-----------------------------------------------------------------------------------------------|--------------|
| `action`        | Either `post` (post one challenge) or `post_all` (post one and continue with the rest).      | `"post"`     |
| `id` / `chaId`  | The challenge ID to start posting from. Can use either `id` or `chaId`.                      | Last ID      |
| `initDelay`     | Time in seconds to wait **before** the first post.                                            | `0`          |
| `betweenDelay`  | Time in seconds to wait **between** multiple posts (only used in `post_all`).                | `7`          |
| `confirmed`     | Boolean (`true` or `false`). Whether to require confirmation before posting.                 | `false`      |

### 📌 Notes

- `id` and `chaId` are treated equivalently.
- If no arguments are provided, the script will prompt for required input interactively.
- `post_all` will continue posting until the earliest challenge (`min(BaseDeDatos.CHALLENGES)`).
- Confirmation is only prompted once at the beginning when using `post_all`.

### ✅ Examples

```bash
python cha.py post
python cha.py post_all id:373
python cha.py action:post_all id:374 initDelay:4
python cha.py action:post_all id:372 initDelay:4 betweenDelay:12 confirmed:true
```
