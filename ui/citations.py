"""Turn a draft's [n] markers into links, for both the Run and Archive pages.

Stored drafts carry one marker per citation, already renumbered by the writer
(`[1][2]`, never `[1, 2]`), and references[n-1] is the URL for [n].
"""
import re

MARKER_RE = re.compile(r"\[(\d+)\]")


def render_draft(draft: str, references: list[str]) -> tuple[str, str]:
    """Returns (draft as markdown with linked markers, numbered references as markdown)."""

    def link(match: re.Match) -> str:
        n = int(match.group(1))
        if 1 <= n <= len(references):
            # \[ \] keep the brackets visible; <url> keeps a ")" in the URL from ending the link
            return rf"[\[{n}\]](<{references[n - 1]}>)"
        return match.group(0)   # no such reference: leave the marker as plain text

    body = MARKER_RE.sub(link, draft)
    refs = "\n".join(f"{n}. <{url}>" for n, url in enumerate(references, start=1))
    return body, refs
