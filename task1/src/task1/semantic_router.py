"""Conservative, registry-independent routing of public financial identities.

This is a financial rule catalog, not a learned universal language model.  A
route needs a unique intent, every named operand with an original source span,
and the complete checkpoint contract.  Numeric positions, case IDs and labels
are not used to choose a route. Existing solved cases bypass this fallback.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Mapping

from src.common.arithmetic import execute, format_value
from src.task1.formulas import reviewed_program
from src.task1.hidden_program import execute as second_execute

N = r"(?P<value>[-+]?\d+(?:\.\d+)?(?:/\d+)?)"
RATE = N + r"\s*(?P<rate_unit>percent|%|basis points?|bps?)(?![A-Za-z])"


@dataclass(frozen=True)
class Route:
    family: str
    intent: tuple[str, ...]
    roles: tuple[tuple[str, str], ...]
    indices: tuple[int, ...]
    topic: str = "financial_identity"


# The regex labels bind financial roles, rather than whichever numbers happen
# to occur first. Range/example numbers in question prose cannot bind roles.
ROUTES = (
    Route("closing_cash_balance", (r"closing cash", r"(?:signed|inflow|outflow)"), (("opening", r"opening cash\s+(?:is|of|=)\s*"+N), ("operating", r"net operating cash flow\s+(?:is|of|=)\s*"+N), ("investing", r"net investing cash flow\s+(?:is|of|=)\s*"+N), ("financing", r"net financing cash flow\s+(?:is|of|=)\s*"+N)), (0,1,2,3)),
    Route("inventory_turnover_days", (r"inventory turnover days", r"365"), (("opening", r"opening inventory\s+(?:is|of|=)\s*"+N), ("purchases", r"purchases\s+(?:are|of|=)\s*"+N), ("closing", r"closing inventory\s+(?:is|of|=)\s*"+N)), (0,1,2)),
    Route("partial_year_disposal", (r"disposal gain or loss", r"straight.line", r"zero residual"), (("cost", r"asset costs\s*"+N), ("life", r"useful life of\s*"+N+r"\s*years"), ("months", r"receives\s*"+N+r"\s*months"), ("years", r"then\s*"+N+r"\s*complete depreciation years"), ("sale", r"sold[^.]*?for\s*"+N+r"\s*USD")), (0,1,2,3,4)),
    Route("dividend_lintner_three_year_avg", (r"three annual EPS", r"adjustment speed", r"shares outstanding"), (("eps1", r"EPS observations are\s*"+N), ("eps2", r"EPS observations are\s*[-+]?\d+(?:\.\d+)?,\s*"+N), ("eps3", r"EPS observations are\s*[-+]?\d+(?:\.\d+)?,\s*[-+]?\d+(?:\.\d+)?,\s*and\s*"+N), ("payout", r"target payout ratio\s+(?:is|=)\s*"+RATE), ("last", r"last year.s dividend per share was\s*"+N), ("speed", r"adjustment speed\s+(?:is|=)\s*"+RATE), ("shares", r"shares outstanding\s+(?:are|=)\s*"+N)), (0,1,2,3,4,5,6)),
    Route("eps_quarterly_pref_buyback", (r"quarterly preferred dividend", r"weighted.average common shares", r"365.day"), (("income", r"net income\s+(?:is|=)\s*"+N), ("preferred", r"preferred shares\s+(?:are|=)\s*"+N), ("dividend", r"quarterly preferred dividend\s+(?:is|=)\s*"+N), ("common", r"beginning common shares\s+(?:are|=)\s*"+N), ("buyback", r"shares repurchased\s+(?:are|=)\s*"+N), ("days", r"repurchased shares were absent for\s*"+N+r"\s*inclusive days")), (1,2,3,4,5,6)),
    Route("capm_wacc", (r"ke\s*=\s*rf\s*\+\s*beta", r"WACC", r"wD"), (("equity", r"common equity E of\s*"+N), ("debt", r"debt D of\s*"+N), ("beta", r"common.equity beta\s+(?:is|=)\s*"+N), ("riskfree", r"risk.free rate rf\s+(?:is|=)\s*"+RATE), ("market", r"market return rm\s+(?:is|=)\s*"+RATE), ("debtcost", r"pretax debt cost kd\s+(?:is|=)\s*"+RATE), ("tax", r"tax rate T\s+(?:is|=)\s*"+RATE)), (0,1,2,3,4,5,6)),
    Route("multi_factor_portfolio", (r"DeFi portfolio", r"staking impact", r"fee impact"), (("portfolio", r"portfolio is valued at\s*"+N), ("allocation", r"staking allocation\s+(?:is|=)\s*"+RATE), ("yield", r"yield boost\s+(?:is|=)\s*"+RATE), ("fee", r"swap.fee effect\s+(?:is|=)\s*"+RATE)), (0,1,2,3), "defi"),
    Route("token_price_calculation", (r"price per token", r"market capitalization", r"circulation"), (("marketcap", r"market capitalization of\s*"+N), ("supply", N+r"\s*token units in circulation")), (0,1)),
    Route("long_call_roi", (r"long call", r"ROI", r"max\(expiration spot"), (("premium", r"premium of\s*(?:USD\s*)?"+N), ("strike", r"strike price\s*(?:USD\s*)?"+N), ("spot", r"underlying is\s*(?:USD\s*)?"+N)), (0,1,2)),
    Route("two_lot_sale_net_profit", (r"lot cost", r"sells all shares", r"net profit"), (("firstcount", r"buys\s*"+N+r"\s*shares"), ("firstprice", r"buys\s*[-+]?\d+\s*shares at USD\s*"+N), ("secondcount", r"and\s*"+N+r"\s*more shares"), ("secondprice", r"more shares at USD\s*"+N), ("sale", r"sells all shares at USD\s*"+N)), (0,1,2,3,4)),
    Route("batch_effective_fee", (r"payment batch", r"effective fee rate", r"per transaction"), (("sales", r"total sales of\s*"+N), ("count", r"across\s*"+N+r"\s*transactions"), ("fixed", r"pricing is\s*"+N+r"\s*USD per transaction"), ("variable", r"plus\s*"+RATE+r"\s*of total sales")), (0,1,2,3)),
    Route("two_phase_semiannual_interest", (r"compounded semiannually", r"first", r"next", r"subtract the original principal"), (("principal", r"USD\s*"+N+r"\s*is compounded"), ("years1", r"first\s*"+N+r"\s*years"), ("rate1", r"first\s*[-+]?\d+\s*years the nominal annual rate is\s*"+RATE), ("years2", r"next\s*"+N+r"\s*years"), ("rate2", r"next\s*[-+]?\d+\s*years it is\s*"+RATE)), (0,1,2,3,4)),
    Route("after_tax_sale", (r"after.tax annual IRR", r"Exactly one year later", r"tax basis"), (("cost", r"investment costs\s*"+N+r"\s*USD"), ("sale", r"sold for\s*"+N+r"\s*USD"), ("tax", r"Capital.gains tax equals\s*"+RATE)), (0,2,3)),
    Route("four_year_annuity_salvage_npv", (r"for four years", r"salvage", r"subtract the initial investment"), (("cost", r"project costs USD\s*"+N), ("saving", r"generates USD\s*"+N+r"\s*at each year.end"), ("salvage", r"USD\s*"+N+r"\s*of salvage"), ("discount", r"annual discount rate of\s*"+RATE)), (0,1,2,3)),
    Route("supply_chain_npv_net_benefit", (r"supply.chain spend", r"NPV savings", r"integration cost"), (("spend1", r"supply.chain spend is\s*"+N), ("spend2", r"supply.chain spend is\s*[-+]?\d+(?:\.\d+)?\s*and\s*"+N), ("reduction", r"annual cost reduction\s+(?:is|=)\s*"+RATE), ("horizon", r"savings horizon\s+(?:is|=)\s*"+N+r"\s*years"), ("discount", r"annual discount rate\s+(?:is|=)\s*"+RATE), ("integration", r"up.front integration cost\s+(?:is|=)\s*"+N)), (0,1,2,3,4,5)),
    Route("credit_rebate", (r"rebate applies", r"strictly greater", r"equality does not qualify"), (("invest", r"buyer invests\s*"+N+r"\s*USD"), ("price", r"credits priced at\s*"+N+r"\s*USD per credit"), ("rebate", r"rebate\s+(?:is|=)\s*"+N+r"\s*USD per purchased credit"), ("threshold", r"strictly greater than\s*"+N+r"\s*credits")), (0,3,6,9)),
)

# Declared money magnitudes are normalized to dollars before evaluating the
# financial identity. Rates retain percentage representation; bp are converted
# to percentage points. Temporal roles retain the identity's years/months/days.
MONEY_ROLES = {
    "closing_cash_balance": {"opening","operating","investing","financing"},
    "inventory_turnover_days": {"opening","purchases","closing"},
    "partial_year_disposal": {"cost","sale"},
    "dividend_lintner_three_year_avg": {"eps1","eps2","eps3","last"},
    "eps_quarterly_pref_buyback": {"income","dividend"},
    "capm_wacc": {"equity","debt"},
    "multi_factor_portfolio": {"portfolio"}, "token_price_calculation": {"marketcap"},
    "long_call_roi": {"premium","strike","spot"},
    "two_lot_sale_net_profit": {"firstprice","secondprice","sale"},
    "batch_effective_fee": {"sales","fixed"},
    "two_phase_semiannual_interest": {"principal"}, "after_tax_sale": {"cost","sale"},
    "four_year_annuity_salvage_npv": {"cost","saving","salvage"},
    "supply_chain_npv_net_benefit": {"spend1","spend2","integration"},
    "credit_rebate": {"invest","price","rebate"},
}
ANSWER_UNITS = {
    "inventory_turnover_days":"days", "eps_quarterly_pref_buyback":"usd_per_count",
    "token_price_calculation":"usd_per_count", "capm_wacc":"percent",
    "long_call_roi":"percent", "batch_effective_fee":"percent", "after_tax_sale":"percent",
}
MONEY_SCALES = {"usd":Fraction(1),"usd_million":Fraction(10**6),"usd_thousand":Fraction(10**3),"usd_billion":Fraction(10**9)}
SLOT_CONTRACTS = {
    "inventory_turnover_days": {"trace_1":("usd",r"cost.of.goods.sold|\bCOGS\b"),"trace_2":("usd",r"average.*inventory"),"trace_3":("times_per_year",r"inventory turnover")},
    "partial_year_disposal": {"trace_1":("usd_per_year",r"annual.*depreciation"),"trace_2":("usd",r"total depreciation"),"trace_3":("usd",r"carrying amount")},
    "dividend_lintner_three_year_avg": {"trace_1":("usd_per_count",r"mean.*EPS|average.*EPS"),"trace_2":("usd_per_count",r"dividend per share")},
    "eps_quarterly_pref_buyback": {"trace_1":("usd",r"annual preferred dividends"),"trace_2":("count",r"weighted.average.*shares")},
    "capm_wacc": {"market_risk_premium_percent":("percent",r"market risk premium"),"capm_equity_cost_percent":("percent",r"equity cost"),"debt_weight":("ratio",r"debt.*weight")},
    "multi_factor_portfolio": {"staking_impact_trace":("usd",r"staking"),"fee_impact_trace":("usd",r"fee")},
    "long_call_roi": {"call_payoff_trace":("usd_per_count",r"payoff"),"net_profit_loss_trace":("usd_per_count",r"profit|loss")},
    "two_lot_sale_net_profit": {"total_shares_trace":("count",r"total shares"),"average_cost_trace":("usd_per_count",r"average cost"),"sale_proceeds_trace":("usd",r"sale proceeds")},
    "batch_effective_fee": {"fixed_fee_total_trace":("usd",r"fixed fees"),"variable_fee_total_trace":("usd",r"variable fees"),"total_fees_trace":("usd",r"total.*fees")},
    "two_phase_semiannual_interest": {"first_growth_trace":("dimensionless",r"first.*growth"),"second_growth_trace":("dimensionless",r"second.*growth"),"ending_balance_trace":("usd",r"ending balance")},
    "after_tax_sale": {"taxable_gain_trace":("usd",r"gain.*tax"),"gain_tax_trace":("usd",r"tax paid"),"after_tax_proceeds_trace":("usd",r"proceeds after tax")},
    "four_year_annuity_salvage_npv": {"year_four_total_trace":("usd",r"year.four.*salvage"),"pv_year_four_trace":("usd",r"present value.*year.four"),"total_pv_trace":("usd",r"total present value")},
    "supply_chain_npv_net_benefit": {"trace_1":("usd",r"annual.*saving"),"trace_2":("usd",r"NPV.*savings")},
    "credit_rebate": {"credits_purchased_trace":("credits",r"purchased quantity"),"eligible_rebate_trace":("usd",r"rebate amount")},
}


def _compatible_unit(actual: str, expected: str) -> bool:
    return actual==expected or expected=="usd" and actual in MONEY_SCALES


def _money_scale(body: str, match: re.Match, route: Route, role: str) -> Fraction:
    """Require recognized USD syntax; do not silently guess absent magnitudes."""
    suffix=body[match.end("value"):]
    prefix=body[match.start():match.start("value")]
    if role in {"eps1","eps2"}:
        last=list(re.finditer(dict(route.roles)["eps3"],body,re.I))
        if len(last)!=1:raise ValueError("ambiguous shared EPS denomination")
        return _money_scale(body,last[0],route,"eps3")
    if role=="spend1":
        shared=re.match(r"\s*and\s*[-+]?\d+(?:\.\d+)?",suffix,re.I)
        if shared:suffix=suffix[shared.end():]
    def check_denominator(after):
        per=re.match(r"\s*per\s+([A-Za-z]+)(?:\s+([A-Za-z]+))?",after,re.I)
        if not per:return
        permitted={
            "dividend_lintner_three_year_avg":{"eps1","eps2","eps3","last"},
            "eps_quarterly_pref_buyback":{"dividend"},
            "long_call_roi":{"premium","strike","spot"},
            "two_lot_sale_net_profit":{"firstprice","secondprice","sale"},
        }
        if role in permitted.get(route.family,set()) and per[1].lower()=="share":return
        if route.family=="batch_effective_fee" and role=="fixed" and per[1].lower()=="transaction":return
        if route.family=="credit_rebate" and role in {"price","rebate"} and (per[1].lower()=="credit" or per[1].lower()=="purchased" and per[2] and per[2].lower()=="credit"):return
        raise ValueError("monetary denominator contradicts financial role")
    unit=re.match(r"\s*(?:(USD)(?:\s+(thousand|million|billion))?|(thousand|million|billion)\s+(USD))\b",suffix,re.I)
    if unit:
        # If a currency is followed by an unknown token, it may be an unknown
        # magnitude or denomination. Only known connective/context words pass.
        after=suffix[unit.end():]
        check_denominator(after)
        nextword=re.match(r"\s+([A-Za-z]+)",after)
        if nextword and nextword[1].lower() not in {"per","across","at","of","and","then","with","in","before","after","now","each"}:
            raise ValueError("unrecognized monetary modifier")
        magnitude=unit[2] or unit[3]
        return MONEY_SCALES["usd_"+magnitude.lower()] if magnitude else Fraction(1)
    if re.search(r"\bUSD\s*$",prefix,re.I):
        # Prefix currency (USD 13 each) is unscaled only when the following
        # token is a known quantity context, rather than an unknown magnitude.
        check_denominator(suffix)
        nextword=re.match(r"\s+([A-Za-z]+)",suffix)
        if nextword:
            token=nextword[1].lower()
            if token in {"thousand","million","billion"}:return MONEY_SCALES["usd_"+token]
            if token not in {"each","per","at","of","now","is"}:raise ValueError("unknown prefix-USD modifier")
        return Fraction(1)
    raise ValueError("missing or unsupported monetary denomination")


def _output_scale(unit: str) -> Fraction:
    if unit in MONEY_SCALES:return MONEY_SCALES[unit]
    if unit in {"days","percent","usd_per_count","usd_per_year","count","ratio","dimensionless","times_per_year","credits"}:return Fraction(1)
    raise ValueError("unsupported result unit")


def _program_values(program: Mapping[str, Any], variables: Mapping[str, Fraction], interpreter=execute):
    values = dict(variables)
    for name, expression in program.get("dag", []):
        values[name] = interpreter(expression, values)
    return interpreter(program["final"], values), {key: interpreter(expr, values) for key, expr in program["slots"].items()}


def solve_semantic(question: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]] | None:
    body = question["question"].split("\n\nAnswer format:")[0]
    if len(body) > 16000 or question["answer_spec"]["type"] != "decimal":
        return None
    candidates = []
    for route in ROUTES:
        if not all(re.search(pattern, body, re.I) for pattern in route.intent):
            continue
        expected_unit=ANSWER_UNITS.get(route.family,"usd")
        answer_unit=question["answer_spec"].get("unit")
        if not _compatible_unit(answer_unit,expected_unit):
            continue
        slots=question["trace_spec"]["slots"]
        expected_slots=SLOT_CONTRACTS.get(route.family,{})
        if len({slot["slot_id"] for slot in slots})!=len(slots) or set(expected_slots)!={slot["slot_id"] for slot in slots}:
            continue
        if any(slot["result_spec"].get("type")!="decimal" or not _compatible_unit(slot["result_spec"].get("unit"),expected_slots[slot["slot_id"]][0]) or not re.search(expected_slots[slot["slot_id"]][1],slot.get("description",""),re.I) for slot in slots):
            continue
        variables, evidence = {}, []
        for (role, pattern), index in zip(route.roles, route.indices):
            matches = list(re.finditer(pattern, body, re.I))
            if len(matches) != 1:
                break
            match = matches[0]
            value = Fraction(match["value"])
            rateunit = match.groupdict().get("rate_unit")
            if rateunit and re.fullmatch(r"basis points?|bps?", rateunit, re.I):
                value /= 100  # Reviewed formulas consume percentages.
            scale=Fraction(1)
            if role in MONEY_ROLES[route.family]:
                try:scale=_money_scale(body,match,route,role)
                except ValueError:break
                value*=scale
            variables[f"x{index}"] = value
            evidence.append({"role": role, "name": f"x{index}", "source_text": match["value"], "start": match.start("value"), "end": match.end("value"), "value": str(value), "rate_unit": rateunit,"money_scale":str(scale)})
        else:
            program = reviewed_program(f"fp.semantic.{route.topic}.{route.family}.intermediate.v1")
            if program is None or set(program["slots"]) != {slot["slot_id"] for slot in question["trace_spec"]["slots"]}:
                continue
            candidates.append((route, variables, evidence, program))
    # Even agreeing ambiguous candidates are rejected: no silent priority rule.
    if len(candidates) != 1:
        return None
    route, variables, evidence, program = candidates[0]
    try:
        final, traces = _program_values(program, variables)
        checked_final, checked_traces = _program_values(program, variables, second_execute)
        if final != checked_final or traces != checked_traces:
            return None
        prediction = {"schema_version": "finreason.task1.prediction/1.0.0", "dataset_version": question["dataset_version"], "case_id": question["case_id"], "final_answer": {"value": format_value(final/_output_scale(question["answer_spec"]["unit"]), question["answer_spec"])}, "steps": [{"slot_id": slot["slot_id"], "value": format_value(traces[slot["slot_id"]]/_output_scale(slot["result_spec"]["unit"]), slot["result_spec"])} for slot in question["trace_spec"]["slots"]]}
        return prediction, {"strategy": "semantic_financial_identity", "family": route.family, "role_bindings": evidence, "program": program, "routing_gate": "unique intent + named source spans + complete slot contract", "independent_reexecution_values": 1+len(traces), "confidence_kind": "structural gate, not calibrated probability"}
    except (KeyError, ValueError, TypeError, ZeroDivisionError, OverflowError):
        return None
