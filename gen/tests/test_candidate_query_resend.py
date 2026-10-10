"""A candidate query lost in the medium is resent with its own MID (series 0256): 2 s and 4.5 s
after the first send while unanswered, twice at most, within em_cli's 8 s wait. The copy is the
same request to an agent, and a second reply is harmless to the controller.

Compiled from the series' own lines, not from assumptions about them: the agent's request
tracker (0196, em_unassoc_query_tracker.h) accepts a copy with the same MID and stations again
and forgets a request once its reply is built, so a copy after a lost reply is measured and
answered again; 0256's resend schedule; and the controller's reply match (upstream, read in the post-series source), a reply taken
only by a radio still waiting with that MID, so a late second reply after the query completed is
matched to nothing (ignored as uncorrelated), never to another query."""
from pathlib import Path
import re
import shutil
import subprocess

import pytest

PATCHES = Path(__file__).resolve().parents[2] / "recipes-ccsp/unified-wifi-mesh/unified-wifi-mesh"
compiler = pytest.mark.skipif(shutil.which("g++") is None, reason="C++ compiler required")


def added_file(patch, path):
    """The whole of a file a patch adds."""
    text = (PATCHES / patch).read_text()
    header = re.search(rf"^\+\+\+ b/{re.escape(path)}(\t.*)?$", text, re.M)   # a timestamp may follow
    body = text[header.end():].split("\n", 1)[1]
    following = re.search(r"^(diff --git|--- )", body, re.M)    # the next file's header
    lines = (body if following is None else body[:following.start()]).splitlines()
    return "\n".join(line[1:] for line in lines if line.startswith("+"))


def added_function(patch, signature):
    lines = [line[1:] for line in (PATCHES / patch).read_text().splitlines()
             if line.startswith("+") and not line.startswith("+++")]
    text = "\n".join(lines)
    start = text.index(signature)
    return text[start:text.index("\n}\n", start) + 3]


def reply_match():
    """The controller's condition for a radio taking a reply: upstream code, as the post-series
    source has it in em_metrics.cpp (handle_1905_ack for the Ack, the response handler for the
    metrics; read at the series' revision, 10 October). An unmatched reply is logged ("Ignoring
    uncorrelated ...") and the handler returns: its m_unassoc_in_progress only guards the
    handler's own run. 0256 must leave both conditions as they are."""
    patch = (PATCHES / "0256-ctrl-candidate-query-resent-with-its-mid-and-logged.patch").read_text()
    removed = [line for line in patch.splitlines() if line.startswith("-") and not line.startswith("---")]
    assert not any("get_unassoc_sta_query_msg_id()" in line or "metrics_pending" in line for line in removed)
    return ("if ((em->get_state() == em_state_ctrl_unassoc_sta_link_metrics_pending) && "
            "(response_msg_id == em->get_unassoc_sta_query_msg_id()))")


def test_the_patch_is_in_the_series_after_0255():
    series = (PATCHES.parent / "unified-wifi-mesh.bbappend").read_text()
    assert series.index("0255-ctrl-an-agent") < series.index("0256-ctrl-candidate-query-resent-with-its-mid") \
        < series.index("0257-cli-candidate-not-ready-submitted-again")
    for name in ("0256-ctrl-candidate-query-resent-with-its-mid-and-logged.patch",
                 "0257-cli-candidate-not-ready-submitted-again.patch"):
        subprocess.run(["git", "apply", "--numstat", str(PATCHES / name)], check=True, capture_output=True)


def test_every_query_is_logged_once_per_event():
    patch = (PATCHES / "0256-ctrl-candidate-query-resent-with-its-mid-and-logged.patch").read_text()
    for line in ("Candidate query start MID %u agent %s radio %s",
                 "Candidate query resend %u MID %u agent %s radio %s after %ld ms",
                 "Candidate query %s MID %u agent %s radio %s resends %u after %ld ms"):
        assert line in patch
    for how in ("answered", "rejected", "expired"):
        assert f'log_unassoc_sta_query_end("{how}");' in patch


@compiler
def test_a_copy_is_the_same_request_and_a_late_reply_matches_nothing(tmp_path):
    tracker = added_file("0196-native-backhaul-steering.patch", "inc/em_unassoc_query_tracker.h")
    schedule = added_function("0256-ctrl-candidate-query-resent-with-its-mid-and-logged.patch",
                              "static bool unassoc_query_resend_due(")
    program = tracker + r'''
#include <cassert>
#include <cstdio>
''' + schedule + r'''
enum em_state_t { em_state_ctrl_configured, em_state_ctrl_unassoc_sta_link_metrics_pending };
struct radio {
    em_state_t state;
    unsigned short mid;
    em_state_t get_state() const { return state; }
    unsigned short get_unassoc_sta_query_msg_id() const { return mid; }
};
static bool takes(const radio *em, unsigned short response_msg_id)
{
    @MATCH@ { return true; }
    return false;
}
int main()
{
    /* the agent: a copy with the same MID and stations is the same request */
    em_unassoc_query_tracker agent;
    std::set<std::string> stations{std::string("\x51\x24" "\x02\x00\x00\x00\x03\x00", 8)};
    assert(agent.insert(7, stations, 1000));
    assert(agent.insert(7, stations, 3000));               /* the copy: accepted, measured again */
    std::set<std::string> other{std::string("\x51\x24" "\x02\x00\x00\x00\x04\x00", 8)};
    assert(!agent.insert(7, other, 3000));                  /* another query under that MID: refused */
    auto replies = agent.accept(7, {}, 3050);
    assert(replies.size() == 1 && replies[0].mid == 7);   /* answered once */
    assert(agent.accept(7, {}, 3060).empty());             /* the copy's measurement: no second reply */
    assert(agent.insert(7, stations, 3500));                /* a copy after a lost reply: answered again */
    assert(agent.accept(7, {}, 3550).size() == 1);

    /* the controller's schedule: 2 s, then 4.5 s, then no more */
    assert(!unassoc_query_resend_due(1999, 0) && unassoc_query_resend_due(2000, 0));
    assert(!unassoc_query_resend_due(4499, 1) && unassoc_query_resend_due(4500, 1));
    assert(!unassoc_query_resend_due(9000, 2));

    /* the controller's match: only a radio still waiting with that MID takes a reply */
    radio waiting{em_state_ctrl_unassoc_sta_link_metrics_pending, 7};
    radio other_query{em_state_ctrl_unassoc_sta_link_metrics_pending, 9};
    assert(takes(&waiting, 7) && !takes(&other_query, 7));
    radio done{em_state_ctrl_configured, 0};               /* answered: MID cleared, state left */
    assert(!takes(&done, 7) && !takes(&other_query, 7));    /* the late copy's reply: ignored */
    std::puts("ok");
    return 0;
}
'''
    program = program.replace("@MATCH@", reply_match())
    source = tmp_path / "model.cpp"
    source.write_text(program)
    built = subprocess.run(["g++", "-std=c++17", "-Wall", "-Werror", "-o", str(tmp_path / "model"), str(source)],
                           capture_output=True, text=True)
    assert built.returncode == 0, built.stderr
    result = subprocess.run([str(tmp_path / "model")], capture_output=True, text=True)
    assert result.returncode == 0 and result.stdout == "ok\n", result.stderr
