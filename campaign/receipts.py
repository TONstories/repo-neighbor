"""Close processed command issues after their outcome is durable on main."""

import json
import subprocess
from run import DIR, HOME, inbox

if __name__ == "__main__":
    results = json.loads((DIR / "ledger.json").read_text())["receipts"]
    for issue in inbox():
        number = issue["number"]
        if str(number) in results:
            # The public ledger is the durable response. Closing is idempotent.
            subprocess.run(
                [
                    "gh",
                    "api",
                    "--method",
                    "PATCH",
                    f"repos/{HOME}/issues/{number}",
                    "-f",
                    "state=closed",
                    "--silent",
                ],
                check=True,
            )
