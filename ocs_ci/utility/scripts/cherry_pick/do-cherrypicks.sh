#!/usr/bin/env bash

upstream=origin
branch_name=$( git rev-parse --abbrev-ref HEAD )
commit=$( git rev-parse HEAD )
github_remote=$( git remote -v |grep -m1 pbalogh |sed 's/.*:\(.*\)\/.*/\1/' )
echo Branch name: $branch_name

trap func exit

function func() {
    git checkout $branch_name
}

releases=${1}

for release in ${releases//,/ }; do
    release_branch="release-$release"
    cherry_pick_branch_name="${branch_name}-release-${release}"
    echo =============================================================
    echo release $release cherry-pick branch: $cherry_pick_branch_name
    echo =============================================================
    git checkout -b $cherry_pick_branch_name
    git reset --hard ${UPSTREAM}/$release_branch
    git cherry-pick $commit
    git push $FORK $cherry_pick_branch_name
    echo *************************************************************
    echo USE THIS LINK TO OPEN PR AGAINST SPECIFIC $release_branch!
    echo "https://github.com/red-hat-storage/ocs-ci/compare/${release_branch}...${github_remote}:ocs-ci:${cherry_pick_branch_name}?expand=1"
    echo *************************************************************
    echo =============================================================
done
