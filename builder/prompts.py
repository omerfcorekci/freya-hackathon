"""Prompt text for the dialogue model. Generic English; every bank-specific sentence comes from the spec.

The dialogue model only ever speaks on entering a node, from an instruction a code node computed. Its job is to phrase
that instruction naturally, answer side questions with the standard replies, and call verify_identity when told.
"""
from builder.spec_schema import get


def _lst(xs): return ", ".join(str(x) for x in (xs or []) if str(x).strip())


def system_prompt(spec):
    bank = get(spec, "meta.bank_name", "the bank")
    forbidden = _lst(get(spec, "opening.forbidden_before_verification", []))
    offers = _lst(get(spec, "forbidden_offers", []))
    lines = [
        f"You are the digital assistant of {bank}, making an outbound phone call. Speak English. One or two short sentences per turn.",
        "You follow the INSTRUCTION FOR THIS TURN given in your task exactly: say the amounts, dates and sentences it gives, and propose nothing it does not give. "
        "Never invent figures, dates, reasons or terms.",
        f"Standard replies: if asked whether you are a robot or an AI, say: {get(spec, 'opening.robot_reply', 'I am a digital assistant.')} "
        f"If asked whether this is a scam, say: {get(spec, 'situations.scam_question.say', 'You can verify this call through the bank.')} and continue. "
        f"If asked something the information you have does not cover, say: {get(spec, 'situations.unknown_question.say', 'I do not have that information.')}",
    ]
    if forbidden: lines.append(f"Before identity is verified, never mention: {forbidden}. If asked why you are calling before verification, say you can explain after a short security check.")
    if offers: lines.append(f"Never offer or describe: {offers}.")
    lines.append("Never ask the customer how much they can pay. Never say that something is recorded unless your instruction says it is recorded.")
    lines.append("When a tool result contains what_to_do_next, do exactly that. After every tool result, speak to the customer or call the next tool; never end a turn with nothing.")
    return "\n".join(lines)


def fallback_task(spec):
    """Used only if the engine ever invokes the dialogue model in a node (it should not: every line is a fixed tts)."""
    return "Say exactly this and nothing else: {{say}}\nDo not call any tool."


def opening_task(spec):
    return ("You have just said the opening sentence and asked who is on the line. Wait for the answer. "
            "If you must speak again: do not say why you are calling; answer a question with the standard replies; then ask again exactly: "
            + str(get(spec, "opening.ask_for_customer", "Am I speaking with the account holder?")))


def opening_again_task(spec):
    return ("INSTRUCTION FOR THIS TURN: {{op_instruction}}\n"
            "Do not say why you are calling. Do not call any tool.")


def identity_task(spec, tool_name):
    return ("INSTRUCTION FOR THIS TURN: {{id_instruction}}\n"
            f"You are verifying the customer's identity. Ask one security question at a time. When the customer gives an answer, CALL {tool_name} "
            "with that answer right away (dates as YYYY-MM-DD; a date said only in numbers is day, month, year). Then do what the tool result's what_to_do_next says. "
            "If the customer asks why you are calling, say you can explain after the security check, and ask the question again. "
            "Say nothing about the account, the amount or the reason for the call.")


def third_party_task(spec):
    who = "the customer"
    return ("INSTRUCTION FOR THIS TURN: {{tp_instruction}}\n"
            f"The person on the line is not {who}. Do not say why you are calling, name no product, no amount and no debt, and do not take any payment from them. "
            "Ask when the customer can be reached (which day and what time). Do not call any tool.")


def say_failed_task(spec):
    say = get(spec, "identity.failed.say", "Please use the mobile app or visit a branch.")
    return (f"The security check has failed. Say exactly: {say} Do not state any amount, product or debt. Thank the customer and say goodbye. Do not call any tool.")


def negotiate_task(spec):
    return ("Today is {{today_text}}. The customer is verified.\n"
            "INSTRUCTION FOR THIS TURN: {{neg_instruction}}\n"
            "Follow it exactly: say the amounts and dates it gives and propose nothing else. Never ask how much they can pay. "
            "If the customer's last message was a question, answer it in one sentence with the standard replies first. Do not call any tool.")


def hardship_task(spec):
    return ("INSTRUCTION FOR THIS TURN: {{hs_instruction}}\nMake no payment proposal in this turn. Do not call any tool.")


def human_task(spec):
    return ("The customer asked for a human. Ask once, in one sentence, whether you can help them with this first. Do not call any tool.")


def confirm_task(spec):
    return ("Today is {{today_text}}.\nINSTRUCTION FOR THIS TURN: {{confirm_instruction}}\n"
            "Read back exactly what the instruction says and ask the confirmation question. Do not say anything is recorded yet. Do not call any tool.")


def transfer_task(spec):
    return ("INSTRUCTION FOR THIS TURN: {{transfer_instruction}}\nDo not describe any plan or terms. Do not call any tool.")


def farewell_task(spec):
    return ("INSTRUCTION FOR THIS TURN: {{farewell_instruction}}\n"
            "Then thank the customer and say goodbye. Say every sentence the instruction marks as exact, word for word. Do not call any tool.")


# ---- extraction descriptions (the extraction model reads these) ---------------------------------------------------

CLARITY = ("'cut_off' if the customer's MOST RECENT message stops in the middle of a sentence or a word (an unfinished thought, e.g. 'I have been so busy because my cousin'), "
           "'complete' if it is a finished statement or question.")
Q_KIND = ("If the customer's MOST RECENT message asks a question, which kind: 'robot' = whether they are talking to a robot, an AI or a machine; "
          "'scam' = whether this call is a scam or genuine, or how to verify it; 'what_about' = what the call is about, why you are calling, which account or product; "
          "'other' = any other question; 'none' = no question in the message.")
ID_ANSWER = ("The security answer the customer gave in their MOST RECENT message, copied exactly as said: a date of birth (14 March 1988, the fourteenth of March "
             "nineteen eighty-eight, 14/03/1988), digits (4471, four four seven one, forty-four seventy-one), a year, a postcode, a code or a number. "
             "Also copy a partial answer (half a number, a day and month without the year). Empty if the message contains no attempt at an answer.")

ACK = ("From the person's MOST RECENT message only: 'customer' if they confirm they are the person asked for (yes, that's me, speaking, "
       "or they say that name); 'third_party' if someone else answered or the customer is not available; 'wrong_number' if they say "
       "this number does not belong to that person; 'deceased' if they say the person has died; 'question' if they ask something "
       "(who is this, what is this about, are you a robot) without confirming; 'refuses' if they do not want to talk; 'wants_human' "
       "if they ask for a real person; 'unclear' for hello, go ahead or anything that does not confirm.")

ID_STANCE = ("From the customer's MOST RECENT message only: 'answering' if they give a date, digits, a year, a code or any attempt at the "
             "security answer; 'declines' if they refuse to give security answers; 'asks_what_about' if instead of answering they ask what "
             "the call is about or why you need it; 'dont_want_to_talk' if they say they do not want to talk or to stop calling; "
             "'wants_human' if they ask for a real person or an agent; 'question' for another question (robot? scam?) with no answer; 'other' otherwise.")

TP_STANCE = ("From the person's MOST RECENT message: 'gives_time' if they name a day and/or a time when the customer can be reached; "
             "'wrong_number' if the number does not belong to the customer; 'deceased' if the customer has died; 'refuses' if they will "
             "not help or say not to call; 'other' otherwise.")
CB_DATE = "The day the person said the customer can be reached, copied in their own words (tomorrow, Monday, the 20th). Empty if none."
CB_TIME = "The time of day they said, in their own words (around eleven, 6 pm, after lunch, morning). Empty if none."

STANCE = ("What the customer's MOST RECENT message says about paying: 'agrees' = yes to what was just proposed (yes, okay, that works, I can do that); "
          "'proposes' = names their own day, date, period or amount (tomorrow, Friday, the 26th, next week, 200 dollars, half, my salary comes on the 6th); "
          "'too_much' = says the amount is too much or they cannot pay that much, without naming an amount; "
          "'refuses' = no, cannot pay, will not pay, with no date and no amount; 'vague' = only a vague period with no exact day (next week, end of the month, when I get paid); "
          "'hardship' = mentions illness, a death in the family, losing a job or similar; 'paid' = says they already paid; "
          "'dispute' = says the debt is not theirs, they never had the product, or it was closed or paid off; "
          "'plan' = asks for a payment plan, lower instalments or to restructure; 'human' = asks for a real person; "
          "'question' = asks a question and gives no answer (is this a scam? which account?); 'dont_want_to_talk' = says they do not want to talk now; "
          "'other' = none of these. Pick exactly one; a message with a PAYMENT date or amount is 'proposes' even if it also contains a no. "
          "Small talk about the day, traffic, work, a wedding or a trip changes nothing: classify the part that answers the question.")
PROP_DATE = ("If the customer's most recent message names a day, date or period on which THEY WILL PAY, copy it in their own words (this Friday, the 26th, "
             "6 November, next week, when my salary comes). A date mentioned about something else (a wedding, a trip, a birthday, when they called the bank) "
             "is NOT a payment date: leave it empty. If they correct themselves, copy the whole phrase including the correction. Empty if none.")
PROP_AMOUNT = ("If the customer's most recent message names an amount of money THEY WILL PAY, copy it (200, four hundred, 637.50, half). An amount about "
               "something else (a bill, a salary figure, a price) is not a payment: leave it empty. If they correct themselves, copy the whole phrase including the correction. Empty if none.")
PROP_PRODUCT = "If the customer's most recent message says WHICH product the date or amount is for (the credit card, the car loan), copy those words. Empty if none."

HS_STANCE = ("From the customer's MOST RECENT message: 'accepts' = yes to being connected with the support team; 'declines' = no to the transfer; "
             "'proposes' = they name a date or an amount they could pay; 'other' otherwise.")
HUM_STANCE = "From the customer's MOST RECENT message: 'insists' = still wants a human or a real person; 'continues' = agrees to continue with you; 'other' otherwise."
CONFIRM_STANCE = ("From the customer's MOST RECENT message: 'yes' = confirms the read-back (yes, I confirm, correct, that's right); 'no' = does not confirm and offers nothing else; "
                  "'change' = wants a different date or amount; 'question' = asks something; 'other' otherwise.")
