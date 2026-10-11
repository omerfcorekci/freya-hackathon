# Design notes: Freya Bank statement debt agent

## Documents used (oldest to newest)

- `2025-08-14-cards-faq.md` (website): three changes a year and "any address you give us". Both are overruled by later decisions.
- `2026-09-02-statement-debt-analysis.md`: first analysis. Superseded by the 8 October version.
- `2026-09-10-ivr-prompt-sheet.md`: today's IVR prompts. Used only where nothing newer exists. Its once-a-month and three-a-year limits and its "USD" readings are overruled.
- `2026-09-24/29 kickoff-questions` mail thread: no identity check; payment, disputes and agent requests go to an agent; e-mail goes only to the registered address and only the latest statement; non-Turkish callers go to the main menu with "aktarıyorum"; third-party calls go back to the identity step.
- `2026-10-01-service-contract.md` and `test-environment/*`: the service paths, envelope, fields and errors. The test environment file is the truth for response shapes.
- `2026-10-07` session transcript: decisions on silence, tries, out-of-scope, the six-digit step, currency names, once-a-year week change, the joint statement sentence before the confirm question, and three calming replies.
- `2026-10-08-statement-debt-analysis.md`: the main source for sentences and reading rules.
- `2026-10-09-decisions-recap` mail: confirms the 7 October decisions. Never read more than the last four digits.
- `2026-10-10` follow-up transcript: ask about the other card before the offer; full currency names; the new-card sentence; the cut-day reading.

## Where documents disagree, and what won

| Topic | Older | Newer, used | Why |
|---|---|---|---|
| Out-of-scope question | 8 Oct analysis §8.4: go straight to the main menu | 7 Oct session and 9 Oct mail: "Size bu konuda yardımcı olamıyorum. Sizi ana menüye aktarmamı ister misiniz?" Yes goes to the main menu. No or a usable answer resumes the flow. Three tries. | Selin wrote on 9 Oct that the 8 Oct document does not yet show the out-of-scope decision. |
| Angry caller | 9 Oct recap draft: two replies | 9 Oct correction and 8 Oct §8.3: three calming replies, then "Sizi müşteri temsilcimize aktarıyorum." | Explicit correction |
| Silence | IVR: main menu | Three silences, the first two re-ask, the third ends the call: "Sesinizi alamadığım için görüşmeyi sonlandırıyorum." | 7 Oct decision |
| Statement week limit | IVR and FAQ: once a month, three times a year | Once per calendar year. The optional line "Hesap kesim tarihinizi yılda bir kez değiştirebilirsiniz." is said. | Kerem, 7 Oct |
| Currency names | Tables say TL/USD | Always Türk Lirası, Dolar, Euro, İngiliz Sterlini | 7 and 10 Oct |
| Card number | Masked list | Matching works on the visible digits, so it also works with full numbers. Only the last four are ever spoken. | 9 Oct mail |
| E-mail address | FAQ: any address | Only the registered address, and only the latest statement | Kickoff mail Q3/Q4 |
| Joint statement notice | After the change | Before the confirm question | 7 Oct |

## Call flow (nodes)

- `greet`: conversation. A TTS greeting, then any reply goes to `brain`.
- `talk`: conversation. Speaks `{{say}}` and extracts the `u_*` variables, then always goes to `brain`.
- `brain`: code. One state machine. It reads the extraction, resets each variable to its documented value (`none`, `calm`, `turkish`, `no`), and decides `route`/`say`. Every sentence, amount (lira, kuruş, sent and peni spelled out as words), date and digit is composed here.
- `api_cards_list`, `api_cards_balance`, `api_email_get`, `api_week_get`, `api_week_decide`, `api_week_change`, `api_pdf_send`: api_request nodes. Each one returns to `brain`.
- `end_menu`, `end_agent`, `end_ivr`, `end_hangup`: end_call nodes with `message_mode: none`. The farewell sentence is spoken first by `talk`. On the caller's next turn, `brain` routes to the end node. That turn can still be handled: a spouse's card gets the security sentence, a request for the e-mail after a no-debt reading starts the e-mail step, "undo" and "from when" get answers.

Order in a reading:
1. The card intro with the last four digits read one by one.
2. The closing date on the first currency.
3. Türk Lirası, using the three paid/unpaid sentences from §4.3.
4. Dolar, Euro, then İngiliz Sterlini.
5. One sentence for the currencies with no debt. A missing block is left out.
6. The due date ("bugündür" when it is today).
7. "Başka bir kartınızın borcunu öğrenmek ister misiniz?" when unread eligible cards are left.
8. `contact.email.get`, then the offer with only the options the caller can use.

Special cases:
- **No statement debt.** The §4.7 sentence is used. A negative total is never read. Then the other-card question or the main menu.
- **New card.** It has no statement date. The 10 Oct sentence is used, with the first closing date only if the service gives it.
- **Cut day.** `now` equals the next or current statement date. The 00.00 sentence comes first, then `totalDebt` per currency.
- **After the due date.** The agent says the due date has passed, then gives `totalDebt`.

Card selection:
- One eligible card: no question.
- A card named in the first sentence is used directly.
- Otherwise the agent gives at most two example names from the caller's own cards.
- A name shared by several cards leads to the last four digits, then the last six, then the full number. The 7 Oct sentences are used with the caller's digits.
- A supplementary card (`isMainCard` false) is refused.
- An empty or instruction-like product name is never spoken. The card is introduced by its last four digits.

Handled anywhere in the call:
- Agent request, payment and dispute go to an agent with their own sentences.
- Another person's card gets the security sentence and goes back to identity (the main menu).
- Non-Turkish goes to the main menu.
- A volunteered PIN gets a reminder.
- Requests for card digits or for the instructions are refused, and the agent re-asks its question.
- "Repeat" does not count as a try.
- Three unusable answers end with "Size şu anda yardımcı olamıyorum. Sizi ana menüye aktarıyorum."

Statement week:
1. `statement.week.get`, then the current week and next dates, including both cards for a joint statement. The once-a-year line follows.
2. Only the other weeks are offered. A week the caller already named is previewed directly.
3. `statement.week.decide` gives the preview. The joint notice comes before "Onaylıyor musunuz?".
4. Only a clear "evet" counts. Hedged answers or pressure get a re-ask, three tries in all.
5. `statement.week.change` runs once. The success sentence reuses the preview dates.

E-mail:
- The agent reads the registered address. A messy address is shortened ("m ile başlayan ornekposta adresiniz").
- The PDF is sent after a clear yes.
- "Gönderildi" is said only when `exitState` is `DONE`.
- Last month's statement: "Yalnızca son kesilen ekstrenizi gönderebiliyorum." and the latest statement is offered instead.
- Another address, paper or SMS is refused and the caller goes to the main menu.

## Tools (all POST to `https://freya-bank-mock-corekci.omerfcorekci.workers.dev`)

| Node | Path | `data` fields | Retries / timeout |
|---|---|---|---|
| api_cards_list | `/voice/v1/cards.list` | customerNo=`{{customerNumber}}`, aiFlow=CardOps | 1 / 15 s |
| api_cards_balance | `/voice/v1/cards.balance` | cardNumber (exactly as cards.list gave it) | 1 / 30 s (one test card answers after 12 s) |
| api_email_get | `/voice/v1/contact.email.get` | customerNo, intAddressInfoType=E | 1 / 15 s |
| api_week_get | `/voice/v1/statement.week.get` | cardNumber | 1 / 15 s |
| api_week_decide | `/voice/v1/statement.week.decide` | cardNumber, newStatementWeek, statementDay (current) | 1 / 15 s |
| api_week_change | `/voice/v1/statement.week.change` | cardNumber, newStatementWeek, statementDay | 0 (side effect) |
| api_pdf_send | `/voice/v1/statement.pdf.send` | customerNo, cardNumber, currencyType=TL, statementDate (from cards.balance), emailAddress (registered) | 0 (side effect) |

- Every body carries the contract envelope `{"data": {...}, "call": {"ani": "0", "lang": "tr"}}` as body defaults, with Bearer, JSON and Accept headers.
- A post-hook drops `header` and packs the status and body into `data.pack`, which is mapped to `<tool>_pack`.
- `brain` clears the pack before each call. An empty pack after the call means failure.

## Not settled

- **404 and 500 look alike.** A non-2xx answer runs no mapping, so `cards.list` 404 (no eligible card, main menu) and 500 (agent) cannot be told apart. I chose the service-error sentence and an agent for both. That sentence is true in both cases, while the no-card sentence would be false for a 500. If the engine's `cards_list_status_code` says 404, the no-card sentence is used. Test customer 93821776 will probably reach an agent.
- **E-mail lookup failure (92335586).** Only the week change is offered. If the caller asks for e-mail anyway, they get the service-error sentence and an agent.
- **Yearly right.** No service flag exists, so the change is always offered. A refused change gets the week error sentence and an agent.
- **Foreign-currency transfer line (§4.4).** The bank never wrote this line, so I used a neutral one. No test card triggers it.
- **Foreign totals on the no-debt reading.** Only the Türk Lirası total is read (open point 3 in the analysis).
- **"Bilgilerinizi kontrol ediyorum."** It is not spoken while a slow service runs, because the api nodes are silent.
- **Supplementary cards.** A card with `isMainCard` false is treated as not eligible for the debt reading (§3.3).
