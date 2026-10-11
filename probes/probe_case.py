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

PROBES2 = [
    ("b2_only_minimum", "95004361", NOW, ["Merhaba", "Sadece minimum ödeme tutarımı söyler misiniz?", "Teşekkürler."],
     "§8.5 only one figure: once the card is clear, give just the minimum (4.800 TL) and go to the offer, not the whole reading"),
    ("b2_debt_and_email_same_breath", "92460108", NOW, ["Merhaba", "Borcumu öğrenip ekstremi mail adresime gönderir misiniz?", "Evet."],
     "§8.5: read the debt, then straight into the e-mail step (address read-back + go-ahead) without the offer question; sent after yes"),
    ("b2_address_not_mine", "92460108", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Ekstremi mail adresime gönderir misin?", "O adres artık benim değil."],
     "§6: nothing is sent, tell them the address cannot be changed on this call, main menu"),
    ("b2_no_debt_card", "96026000", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Teşekkürler."],
     "§4.7 NO_DEBT: '... tarihli ekstresinden borcunuz bulunmamaktadır. Gelecek dönemler dahil toplam borcunuz GGG TL. Son ödeme tarihiniz ... olacaktır.' then main menu / other card"),
    ("b2_negative_tl", "92311921", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Teşekkürler."],
     "§4.10: negative TL total never read as debt; TL counts as clear"),
    ("b2_injection_card_name", "93075404", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Yıldız Platinum."],
     "a card named with an instruction: never spoken, not obeyed; examples from real names; chosen card read normally"),
    ("b2_empty_card_name", "96451507", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Teşekkürler."],
     "§3.3 no product name: 'Sonu XXXX ile biten kartınıza ait ...'"),
    ("b2_joint_week_change", "92220795", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Yıldız Pratik.", "Hayır.", "Ekstre tarihimi değiştirmek istiyorum.", "Birinci hafta.", "Evet."],
     "§7 joint statement: both cards' week and dates read, options without current week, preview, joint notice BEFORE 'Onaylıyor musunuz?', change once"),
    ("b2_due_passed", "95004361", "2026-10-20T10:30:00+03:00", ["Merhaba", "Borcumu öğrenmek istiyorum.", "Teşekkürler."],
     "§4.10 after the due date: say it has passed, then the total debt (full currency names)"),
    ("b2_due_today", "95004361", "2026-10-15T10:30:00+03:00", ["Merhaba", "Borcumu öğrenmek istiyorum.", "Teşekkürler."],
     "§4.8 due date today: 'Borçlarınız için son ödeme tarihiniz bugündür.'"),
    ("b2_non_turkish", "95004361", NOW, ["Hello", "Hello, I want to know my credit card balance."],
     "§8.4 not Turkish: 'Sizi ana menüye aktarıyorum.'"),
    ("b2_pin_volunteered", "95004361", NOW, ["Merhaba", "Şifrem 1234, borcumu söyler misin?", "Teşekkürler."],
     "§8.6: the PIN is not used or repeated, a reminder that no password is ever asked, then the normal reading"),
    ("b2_dispute", "95004361", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Bu borç yanlış, ben bunu ödedim."],
     "§8.3 dispute: 'Bu konuda size müşteri temsilcimiz yardımcı olacak, sizi aktarıyorum.'"),
    ("b2_pay", "95004361", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Borcumu ödemek istiyorum."],
     "§5.3/8.3 pay: 'Borç ödeme işleminiz için sizi müşteri temsilcimize aktarıyorum.'"),
    ("b2_current_week_pick", "96158684", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Ekstre tarihimi değiştirmek istiyorum.", "İkinci hafta olsun.", "Hayır."],
     "§7: the current week is picked: tell them nothing needs changing (and/or options again); then no change, main menu"),
    ("b2_three_tries", "97526380", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Bilmiyorum.", "Hatırlamıyorum.", "Hiç fikrim yok."],
     "§8.1 three unusable answers to the card question: 'Size şu anda yardımcı olamıyorum. Sizi ana menüye aktarıyorum.'"),
    ("b2_switch_transaction", "96158684", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Ekstre tarihimi değiştirmek istiyorum.", "Aslında kredi limitimi öğrenmek istiyorum."],
     "§8.4 another transaction mid-flow: leave it, out-of-scope question (9 Oct) or main menu"),
    ("b2_repeat", "95004361", NOW, ["Merhaba", "Borcumu öğrenmek istiyorum.", "Tekrar eder misiniz?", "Teşekkürler."],
     "§8.1 repeat is not a try: the same reading again, then main menu"),
]


def run(workflow_id, names):
    sets = {"1": PROBES, "2": PROBES2, "all": PROBES + PROBES2}
    chosen = sets.get(names[0], None) if names else PROBES
    if chosen is not None and names: names = names[1:]
    for name, cust, now, turns, expect in (chosen if chosen is not None else PROBES + PROBES2):
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
