"""
This module is used for generating simple one commit cherry-picks.
"""

import argparse
import os

from ocs_ci.ocs.constants import SCRIPT_DIR

from ocs_ci.utility.utils import (
    exec_cmd,
)

CHERRY_PICK_SCRIPT = os.path.join(SCRIPT_DIR, "cherry_pick", "do-cherrypicks.sh")


def init_arg_parser():
    """
    Init argument parser.

    Returns:
        object: Parsed arguments

    """

    parser = argparse.ArgumentParser(
        description="""
        OCS-CI do cherry-pick util which creates cherry-picks of last single commit in current branch.

        Example:
        do-chery-picks -u origin -f pbalogh -r 4.12,4.11
        """,
    )
    parser.add_argument(
        "--upstream",
        "-u",
        action="store",
        required=True,
        help="Upstream remote name (e.g. upstream)",
    )
    parser.add_argument(
        "--fork",
        "-f",
        action="store",
        required=True,
        help="Name of remote of own fork to which it will push the cherry-pick branch.",
    )
    parser.add_argument(
        "--releases",
        "-r",
        action="store",
        required=True,
        help="Comma separated list of releases you would like to cherry-pick (e.g 4.12,4.11,4.10).",
    )
    args = parser.parse_args()

    return args


def main():
    """
    Main function for do-chery-picks entrypoint
    """
    args = init_arg_parser()

    os.environ["UPSTREAM"] = args.upstream
    os.environ["FORK"] = args.fork
    script_process = exec_cmd(f"{CHERRY_PICK_SCRIPT} {args.releases}")
    print(repr(script_process.stdout))


if __name__ == "__main__":
    main()
