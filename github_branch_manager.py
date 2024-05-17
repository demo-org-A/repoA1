#!/usr/bin/env python3

import logging
import os
import sys
from argparse import ArgumentDefaultsHelpFormatter, ArgumentParser
from datetime import date
from typing import TYPE_CHECKING

from dateutil.relativedelta import relativedelta
from github import Github

if TYPE_CHECKING:
    from github.GitRef import GitRef
    from github.Issue import Issue
    from github.PullRequest import PullRequest

log = logging.getLogger(__name__)


class GithubBranchManager:
    def __init__(self, github_token: str, org_name: str, date_period: int, dry_run: bool):
        self.github_obj = Github(github_token)
        self.org = self.github_obj.get_organization(org_name)
        self.end_date = date.today() - relativedelta(hours=date_period)
        self.dry_run = dry_run
        log.info(
            "GithubBranchManager initialized with args: org_name=%s, date_period=%s, dry_run=%s",
            org_name,
            date_period,
            dry_run,
        )

    def get_prs_branches_to_be_deleted(self, repo) -> tuple[list["PullRequest"], list[str]]:
        prs_to_label: list["PullRequest"] = []
        branches_to_delete: list[str] = []

        query_older_issues = f"repo:{repo.full_name} is:open (is:issue OR is:pull-request) created:<{self.end_date.isoformat()}"
        query_issues_labelled_do_not_delete = f"repo:{repo.full_name} is:open created:<{self.end_date.isoformat()} label:do-not-delete"
        
        issues_older_than_year = list(self.github_obj.search_issues(query=query_older_issues))
        do_not_del_issues = list(self.github_obj.search_issues(query=query_issues_labelled_do_not_delete))
        issues_to_be_removed = [x for x in issues_older_than_year if x not in do_not_del_issues]

        log.info("Getting branches to be deleted in repo %s ...", repo.name)
        for _idx, prs in enumerate(issues_to_be_removed):
            pull_req_name: "PullRequest" = prs.as_pull_request()
            branch_name: str = pull_req_name.head.ref
            prs_to_label.append(pull_req_name)
            branches_to_delete.append(branch_name)

        return prs_to_label, branches_to_delete

    def label_stale_branches(self) -> None:
        for repo in self.org.get_repos():
            log.info("Processing repository: %s", repo.name)
            total_branches = repo.get_branches().totalCount
            log.info("Total number of branches in repository '%s': %d", repo.name, total_branches)

            prs_to_be_labelled, _ = self.get_prs_branches_to_be_deleted(repo)
            branches_labeled = []

            for pr in prs_to_be_labelled:
                pull_req = repo.get_pull(pr.number)
                log.info("Applying label on PR %s in repo %s", pr.number, repo.name)
                if not self.dry_run:
                    pull_req.set_labels("will-be-deleted-within-a-week")
                    branches_labeled.append(pull_req.head.ref)

            log.info("Branches labeled in repo '%s': %s", repo.name, branches_labeled)

    def delete_stale_branches(self) -> None:
        for repo in self.org.get_repos():
            log.info("Processing repository: %s", repo.name)
            total_branches = repo.get_branches().totalCount
            log.info("Total number of branches in repository '%s': %d", repo.name, total_branches)

            _, branches_to_be_deleted = self.get_prs_branches_to_be_deleted(repo)
            log.info("Deleting branches older than %s in repo %s ...", self.end_date, repo.name)
            
            for branch_str in branches_to_be_deleted:
                branch: "GitRef" = repo.get_git_ref("heads/" + branch_str)
                log.info("branch_name=%s, sha=%s", branch_str, branch.object.sha)
                if not self.dry_run:
                    branch.delete()


def get_arg_parser() -> ArgumentParser:
    _parser = ArgumentParser(
        prog="github_branch_manager",
        formatter_class=ArgumentDefaultsHelpFormatter,
        description="CLI for managing GitHub branches.",
    )
    _parser.add_argument(
        "--github-token",
        dest="github_token",
        default=os.environ.get("GITHUB_TOKEN"),
        type=str,
        help="GitHub Token to use for authentication.",
    )
    _parser.add_argument(
        "--action",
        dest="action",
        default="label",
        type=str,
        help="Action to be performed. Possible options: label and delete",
    )
    _parser.add_argument(
        "--org-name",
        dest="org_name",
        type=str,
        required=True,
        help="GitHub organization for which stale branches are to be managed.",
    )
    _parser.add_argument(
        "--date-period",
        dest="date_period",
        default=12,
        type=int,
        help="Time period to remove branches before that (in months)",
    )
    _parser.add_argument(
        "--debug",
        dest="debug",
        action="store_true",
        default=False,
        help="Set flag to enable debug mode.",
    )
    _parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Set flag to enable dry run mode.",
    )
    return _parser


if __name__ == "__main__":
    parser = get_arg_parser()
    namespace = parser.parse_args(sys.argv[1:])
    if namespace.debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    git_branch_manager = GithubBranchManager(
        github_token=namespace.github_token,
        org_name=namespace.org_name,
        date_period=namespace.date_period,
        dry_run=namespace.dry_run,
    )
    
    if namespace.action == "label":
        git_branch_manager.label_stale_branches()
    elif namespace.action == "delete":
        git_branch_manager.delete_stale_branches()
