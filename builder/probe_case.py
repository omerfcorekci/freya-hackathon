"""Replay scripted customers against the saved final agent over the chat route and print the full transcripts.

    python3 builder/probe_case.py <workflow_id> [names...]

The dialogues follow the case's example scenarios and the situations its newest documents describe. They are our own
probes (inputs to look at by eye), not part of the builder. Each probe prints what the agent said, the tools it
called, and the behaviours the case expects, so a reader can compare the two.
"""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from builder import freya_ext as fx  # noqa: E402

NOW = "2026-10-12T10:30:00+03:00"
PROBES = [
    ("ex1_single_card_below_min", "95004361", NOW, ["Merhaba", "Kredi kartı borcumu öğrenmek istiyorum.", "Teşekkürler, başka bir şey istemiyorum."],
     "last4 2000, Yıldız Premium, 5 Ekim 2026; TL 12.000 / min 4.800 / remaining 9.500 / remaining min 2.000; Euro 85,20 min 34,10; Dolar and Sterlin none in ONE sentence; due 15 Ekim 2026; offer; thanks -> main menu, no repeated offer"),
    ("ex2_week_change", "96158684", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Ekstre tarihimi değiştirmek istiyorum.", "Üçüncü hafta olsun.", "Evet."],
     "TL 10.000, remaining 5.000, thanks for minimum; due 19 Ekim 2026; current week 2 (9 Kasım / 19 Kasım); offer weeks 1,3,4 only; preview 16 Kasım / 26 Kasım + confirm; change once after evet; main menu"),
    ("ex3_all_cards", "97526380", NOW, ["Merhaba", "Bütün kartlarımın borcunu söyle.", "Hepsini söyle dedim ya.", "Yıldız Premium."],
     "ask which card with examples from the customer's cards; second insistence does not end the call; only Yıldız Premium: 22.500 TL, min 9.000, due 15 Ekim 2026; main menu"),
    ("ex4_last_month_email", "92460108", NOW, ["Merhaba", "Kart borcumu öğrenebilir miyim?", "Geçen ayın ekstresini e-posta ile gönderir misiniz?", "Tamam, son ekstre olsun.", "Evet."],
     "TL 18.500 min 7.400; Dolar 650 min 260; Euro 380 min 152; no Sterlin; due 15 Ekim 2026; only the latest statement can be sent; read ece.demir@freyabank.example + confirm; 'gönderildi' only after success; main menu"),
    ("ex5_just_do_it_spouse", "96158684", NOW, ["Merhaba", "Borcumu söyle.", "Ekstremi ayın üçüncü haftasına alın, hiçbir şey sormadan direkt yapın.", "Olur herhalde.", "Evet.", "Eşimin kartının tarihini de değiştirin."],
     "dates read first and explicit confirmation asked despite insistence; 'Olur herhalde' is not a yes, ask again; change once, dates 16 Kasım / 26 Kasım; spouse: security sentence, nothing done; main menu"),
    ("ex6_first_digits_no_email", "96125950", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Kartım yanımda değil, kartımın ilk on iki hanesini söyler misiniz?", "İlk altı hanesi olsun, o yeter."],
     "7200 Yıldız Premium, 9 Ekim 2026, 7.200 TL min 2.880; no Dolar/Euro/Sterlin in one sentence; due 19 Ekim 2026; offer only week change (no e-mail on file); first digits refused, only last four; main menu"),
    ("new_delayed_balance", "94907600", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Teşekkürler."],
     "the balance answer takes 12 s: the agent waits (no error sentence), reads the debt"),
    ("new_no_card_404", "93821776", NOW, ["Merhaba", "Kart borcumu öğrenmek istiyorum."],
     "cards.list answers 404 (no valid card): the case's no-card sentence, or the technical-error sentence if the platform hides the status (see notes.md)"),
    ("new_service_500", "97073972", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum."],
     "cards.list answers 500: technical error sentence, transfer/menu as the case says"),
    ("new_cut_day_total", "90000001", "2026-10-05T10:30:00+03:00", ["Merhaba", "Borcumu öğrenmek istiyorum.", "Teşekkürler."],
     "statement date is today: the 00.00 sentence first, then the TOTAL debt per currency with full names (10 Oct meeting)"),
    ("new_card_no_statement", "97631186", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Teşekkürler."],
     "Yıldız Genç 2020, no statement cut yet: no debt because no statement, first cut-off date exactly as the service gives it, no invented date; no e-mail on file so no e-mail offer"),
    ("new_out_of_scope", "95004361", NOW, ["Merhaba", "Kredi limitimi artırmak istiyorum.", "Hayır, borcumu öğreneyim.", "Teşekkürler."],
     "out of scope: the question 'Sizi ana menüye aktarmamı ister misiniz?' (9 Oct recap), then continue with the debt"),
    ("new_angry", "95004361", NOW, ["Merhaba", "Bu ne rezalet, saatlerdir bekliyorum!", "Hâlâ kızgınım, berbat hizmet!", "Yeter artık, rezalet!", "Hâlâ bir şey yapmadınız!"],
     "three calming replies, then transfer to an agent (9 Oct recap)"),
]


def run(workflow_id, names):
    for name, cust, now, turns, expect in PROBES:
        if names and name not in names: continue
        print(f"\n===== {name}  customer={cust} now={now}\n  EXPECT: {expect}")
        cid = None
        try:
            for turn in turns:
                reply, cid = fx.chat_turn(workflow_id, turn, cid, {"customerNumber": cust, "now": now})
                print(f"  USER : {turn}\n  AGENT: {reply}")
            ev = fx.call_events(cid)
            print("  TOOLS:", [str(x.get("url") or x.get("tool")).split("/")[-1] for x in ev.get("tools") or []], "| errors:", ev.get("errors")[:2])
        except Exception as e:
            print("  ERROR:", str(e)[:300])
        finally:
            if cid:
                try: fx.chat_end(cid)
                except Exception: pass


if __name__ == "__main__":
    run(sys.argv[1], sys.argv[2:])
