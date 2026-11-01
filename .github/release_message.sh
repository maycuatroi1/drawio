#!/usr/bin/env bash
# Release notes of a tag (default: the newest one): the commits since the tag before it.
tag=${1:-$(git describe --tags --abbrev=0)}
previous_tag=$(git describe --tags --abbrev=0 "${tag}^" 2>/dev/null)
git shortlog "${previous_tag:+${previous_tag}..}${tag}" | sed 's/^./    &/'
