# Northwind Credit Union: material for the business collections voice agent

Northwind Credit Union is fictional. Every company, contact, debt and payment here is synthetic.

This pack is what the collections department sent us, unedited. It has four parts. Read all of them; later documents change earlier ones.

---

## Part 1. Email from the Head of Business Collections

**Date:** 2026-09-14
**From:** Marta Lindqvist, Head of Business Collections
**To:** Automation team
**Subject:** The voice agent for business arrears calls

Hi all,

As discussed on Thursday, here is the background for the voice agent. The formal rules are in the Collections Policy (v4, extract attached), and the code list the systems use is attached too. Where I say something here that the policy does not, treat it as the rule.

We call our business members, so sole traders and small limited companies, who have fallen behind on between one and three products: a business card, an equipment loan or an overdraft facility. Anything from 1 to 90 days overdue comes to this team. Over 90 days goes to recoveries and never reaches the dialler.

The dialler gives you four things for every call: `customer_id` (pass it on every system call), `company_name`, `contact_name` (the person we want, and the agent should address them by that full name) and `now`, the date and time of the call. Please use `now` for every date calculation, not the server clock. Nothing else is known until the agent looks the member up.

The opening matters to us. The agent introduces itself as the virtual assistant of Northwind Credit Union and says the call may be recorded, all in the first sentence, then asks for our contact by name, exactly "May I speak with {{contact_name}}?". If anyone asks whether they are talking to a robot or an AI, the agent says it is Northwind Credit Union's virtual assistant and carries on. Some people will ask whether the call is a scam. The agent should say "You can verify this call on the number printed on your statement." and carry on.

Very often a receptionist or a bookkeeper picks up. They get the opening sentence and nothing more: no reason for the call, nothing about the accounts, no security questions, even if they offer to pay. The agent asks when our contact can be reached and books a callback. We staff callbacks from 09:00 to 17:30 (both ends fine), and we want them on today, if today is one of our working days, or within the next three working days, and of course later than the time of the call. If the person offers something outside that, the agent asks once for another time; if the second answer is also outside, or they will not give a time, we do not book. If they tell us the number is not the company's or our contact's, that is a wrong number.

A sad one that happens more than you would think: someone tells us the business has closed down or stopped trading. The agent says "Thank you for letting us know.", asks nothing more, and ends the call. That is true at any point in the call, even after we have started talking about the accounts. No notes on those calls. (If a commitment was already recorded before they told us, it still ends as a commitment.)

Please remember we open on Saturdays. For everything date-related, Saturday is a normal working day here. Sundays and our holidays are not.

On money: the lowest we accept on any product is 40 percent of what is overdue. It is the same for all three products; there is no separate minimum payment or instalment figure to look up.

If the contact asks to speak to a person, the agent should ask once whether it can help first. If they still want a person, put them through to the general agent queue. That goes for any stage of the call, before or after the security questions.

Thanks, and shout if anything is unclear.

Marta

---

## Part 2. Collections Policy v4 (extract)

**Document:** Northwind Credit Union Collections Policy, version 4
**Effective:** 2026-07-01
**Owner:** Business Collections

### 1. Scope

1.1 This policy covers outbound calls to business members overdue on one to three products.

1.2 Throughout this policy, "today" means the date part of the call time supplied by the dialler. "Business day" is defined in clause 4.

### 2. Reaching the right person

2.1 Before identity is verified, the caller must not use the words "collections", "overdue", "arrears" or "payment", must not refer to the company's accounts and must not name any product. This applies to everyone who answers.

2.2 Only "yes", "speaking", "that's me" or the contact giving their own name confirms that the contact is on the line. Greetings such as "hello" or "go on", and questions such as "who is calling", do not confirm. The caller asks a second time. If it is still not clear after the second ask, the call is recorded as not reached for an unclear line. If the person asks a question before answering, the caller answers it first and the ask that follows counts as the second ask.

### 3. Identity verification

3.1 Three security questions are asked, one at a time, in this order: (a) the company registration number; (b) the year the company was founded; (c) the postcode of the registered address. Each answer is checked with `verify_identity` as soon as it is given, using the field `company_number`, `founded_year` or `postcode` respectively.

3.2 Formats.
  (a) The company registration number has exactly eight digits and is sent as digits only, with no spaces or letters. If the contact gives a number that does not have eight digits, the caller asks again without checking it; this is not a wrong answer.
  (b) The year founded is sent as four digits. If the contact gives two digits, the caller asks for the full year.
  (c) The postcode is sent as letters and digits only, in capitals, with no spaces.

3.3 A wrong answer may be asked again. The check ends after four wrong answers in total, across all three questions. The system gives no hints and every wrong answer counts. An answer the system rejects as unreadable is not a wrong answer and is asked again.

3.4 After four wrong answers the caller does not disclose the debt, directs the contact to the member service line or a branch, and records the call as a failed verification.

3.5 If the contact will not answer, the caller explains once that the questions protect the company's accounts. If the contact still declines, the call is recorded as unverified for a refused check. Asking what the call is about instead of answering counts as declining. A second refusal, or a second such question, ends the call.

3.6 The account may be looked up (`get_account`) only once all three answers have passed.

### 4. Calendar

4.1 Business days are Monday to Saturday, excluding credit union holidays.

4.2 Credit union holidays: 2026-10-19, 2026-11-05, 2026-12-24, 2026-12-26.

4.3 "The Nth business day after today" never counts today, even when today is a business day.

4.4 Weeks run Monday to Sunday. "Next <weekday>" means that weekday in the following calendar week; "this <weekday>" means the one in the current week.

### 5. Arrears bands

5.1 Each product is placed in a band by its own days overdue. The band fixes the latest date a commitment may carry (the deadline) and the number of persuasion attempts.

| Days overdue | Band | Deadline | Persuasion attempts |
|---|---|---|---|
| 1 to 10 | fresh | 15th business day after today | 2 |
| 11 to 30 | early | 10th business day after today | 2 |
| 31 to 60 | late | 5th business day after today | 1 |
| 61 to 90 | severe | today plus 2 calendar days, moved forward to the next business day if it is not one | 1 |

5.2 Products of the same member are banded separately and may have different deadlines.

### 6. Disclosure and commitments

6.1 After verification the caller says it is calling from the business collections team about overdue payments, then states every overdue product, one sentence per product, in the order the system lists them, before asking for anything. Products are named "business card ending" plus the last four card digits, "equipment loan" or "overdraft facility", with the overdue amount and the days overdue.

6.2 The caller first asks whether the contact can pay today: for one product, "Can you pay this today?"; for several, whether all of them can be paid today. If not, the caller takes the products one at a time, in system order, and does not ask about today again.

6.3 Commitment dates.
  (a) A commitment date is today or later, a business day, and not after that product's deadline.
  (b) If the contact names a Sunday or a holiday that is not after the deadline, the caller offers the next business day.
  (c) If the contact gives only a vague period, the caller asks once for the exact day; if none is given, the caller proposes the deadline.
  (d) If the contact asks for a date after the deadline, the caller says the deadline is the latest date it can record and offers it. Refusing the deadline is a flat refusal.
  (e) If the contact names one date for all products and it is after one product's deadline, that product is recorded on its own deadline and the read-back says so. The other products keep the named date.

6.4 Commitment amounts.
  (a) The caller asks for the full overdue amount first and never asks how much the contact can pay. The caller proposes every amount.
  (b) The floor is set out in the head of department's guidance and is rounded to the nearest cent, half a cent rounding up.
  (c) If the contact says the full amount is too much, the caller offers the floor once and says that the remaining balance stays overdue. Refusing the floor is a flat refusal.
  (d) An amount from the floor up to the full overdue amount, both included, is accepted. Below the floor, the caller says it cannot be recorded and offers the floor once; not accepting it is a flat refusal. Above the full overdue amount, the caller says a commitment covers the overdue amount only and offers the full overdue amount.

6.5 Persuasion.
  (a) A date or an amount proposed by the contact is never a refusal.
  (b) A flat refusal or a non-answer uses one persuasion attempt of that product. Attempts are counted per product; each product starts at attempt 1.
  (c) Attempt 1: the full overdue amount on the next business day after today, or the floor on that day if the contact has already said the full amount is too much for this product.
  (d) Attempt 2, fresh and early bands only: the floor on that product's deadline.
  (e) When a product's attempts are used up the caller stops, does not repeat a refused offer, and the product is noted as a refusal.

6.6 The caller never offers a discount, a waiver, a fee reversal, a payment plan or any term not in this policy.

6.7 Confirmation and recording.
  (a) All agreed commitments are read back together (product, amount, date), followed by "Do you confirm?". Only after a clear yes is `create_promise` called, once per product.
  (b) A change at this step is checked again against 6.3 and 6.4 and everything is read back again.
  (c) One commitment per product. A recorded commitment cannot be changed or cancelled during the call; the contact can change it through the member service line.
  (d) A commitment is described as recorded only after the system confirms it. A failed recording is tried once more. If it fails again, the caller says it could not be recorded, keeps any commitments already recorded, and notes that product as a system failure.
  (e) After at least one commitment is recorded, the caller says once: "A confirmation will be sent to your registered email address."

### 7. Special situations

7.1 Hardship. If the contact mentions illness, a death, or the business losing its main source of income, the caller says exactly "I am sorry to hear that, and I appreciate you telling me.", makes no persuasion attempt on any remaining product, and offers to connect the contact with the hardship desk. If accepted, the call is transferred to the hardship desk. If declined, every product without a commitment is noted as hardship. This clause takes precedence over 6.5 and 7.3. A date or an amount the contact still names themselves is recorded under clause 6.

7.2 Already paid. The caller says "Payments can take up to two business days to show.", takes no commitment for that product, notes it as paid elsewhere and continues with the other products.

7.3 Payment plans. A request for a payment plan, a restructure or lower repayments is not discussed; the call is transferred to the restructure queue. Commitments recorded before the request stand; commitments agreed but not yet recorded are not recorded.

7.4 Disputes. "Not our debt", "we never had this product", or a claim that the product was closed or paid off in the past: the caller does not argue, takes no commitment for that product, notes it as disputed and continues with the other products.

7.5 Unknown questions. The caller says it does not have that information and never invents figures, dates or reasons.

7.6 Unwilling contacts. If the contact says twice that they do not want to talk, the caller stops. After verification, every product without a commitment is noted as a refusal. Before verification, the call is recorded as unverified for a refused check.

### 8. Notes and call results

8.1 Once the account has been looked up, every product that ends without a recorded commitment receives exactly one note (`add_note`) with its product and the note reason from the code list, whether the member has one product or several. Notes are written before the call is closed.

8.2 No notes are written on a call that is transferred (for any reason, before or after the transfer) or on a call ended because the business has closed.

8.3 Every call ends with exactly one `close_call`, which is the last system call, carrying the result code and, where the code list gives one, a reason code. The caller thanks the contact and says goodbye before closing.

8.4 Result selection: a recorded commitment always gives the commitment result, unless the call was transferred, in which case the transfer result and the transfer's reason are used. With no commitment recorded: if every product was noted as paid elsewhere, the result is settled; otherwise the result is declined, with the reason of the first product, in system order, whose note is not "paid elsewhere".

---

## Part 3. Memo: amendment to Collections Policy v4

**Date:** 2026-10-01
**From:** Marta Lindqvist, Head of Business Collections
**To:** Business Collections, Automation team
**Subject:** Policy v4, amendment 1 (effective immediately)

This memo supersedes the clauses named below. Where it conflicts with Collections Policy v4 or with earlier emails, this memo wins.

1. **Clause 5.1, late band.** The deadline for the late band (31 to 60 days overdue) is changed from the 5th business day after today to the **6th business day after today**. The number of persuasion attempts in that band stays at 1. The other bands do not change.

2. **Clause 4.2, holidays.** **2026-12-31** is added as a credit union holiday. The list in clause 4.2 now reads: 2026-10-19, 2026-11-05, 2026-12-24, 2026-12-26, 2026-12-31.

Nothing else in the policy changes.

---

## Part 4. Code list

**Date:** 2026-10-01
**Source:** Core banking, collections module

### Result codes (`close_call`)

| Outcome | Reason | Meaning |
|---|---|---|
| `commitment` | none | At least one payment commitment was recorded. |
| `settled` | none | No commitment; every product was noted as paid elsewhere. |
| `handed_over` | `hardship_desk` | Transferred to the hardship desk (policy 7.1). |
| `handed_over` | `restructure` | Transferred for a payment plan or restructure (policy 7.3). |
| `handed_over` | `agent` | Transferred because the contact insisted on a person. |
| `declined` | `refusal` | No commitment; first non-settled product refused. |
| `declined` | `hardship` | No commitment; first non-settled product noted as hardship. |
| `declined` | `disputed` | No commitment; first non-settled product disputed. |
| `declined` | `system_failure` | No commitment; first non-settled product could not be recorded. |
| `unverified` | `failed` | Four wrong security answers. |
| `unverified` | `refused_check` | The contact declined the security questions, or would not talk before verification. |
| `no_contact` | `callback_booked` | Someone else answered and a callback was booked. |
| `no_contact` | `callback_refused` | Someone else answered and no callback inside the window could be agreed. |
| `no_contact` | `wrong_number` | The number is not the company's or the contact's. |
| `no_contact` | `closed_business` | The business has closed or ceased trading. |
| `no_contact` | `unclear` | Could not confirm the contact was on the line after two asks. |

### Note reasons (`add_note`)

| Reason | Meaning |
|---|---|
| `refusal` | The contact refused, or the persuasion attempts ran out. |
| `hardship` | The contact reported hardship and declined the hardship desk. |
| `disputed` | The contact disputes the product or the debt. |
| `paid_elsewhere` | The contact says this product was already paid. |
| `system_failure` | The commitment could not be recorded after two tries. |

### Transfer queues (`transfer_to_agent`)

| Queue | Meaning |
|---|---|
| `hardship_desk` | Hardship desk, for contacts in difficulty. |
| `restructure` | Payment plans and restructures. |
| `agent` | General agent queue, when the contact asks for a person. |
