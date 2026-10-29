"""Inference reads a trained program registry, never answer labels."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from src.common.arithmetic import execute, format_value
from src.task1.templates import bind


class Solver:
    def __init__(self, registry_path: Path, *, use_explicit: bool = True, use_reviewed: bool = True, use_policy: bool = True, use_hidden: bool = True, use_semantic: bool = True, use_equations: bool = True, use_linear_systems: bool = True, use_financial_graph: bool = True, use_local_model: bool = True) -> None:
        self.registry = json.loads(registry_path.read_text(encoding="utf8"))["programs"]
        from src.task1.registry_contracts import Contracts
        self.contracts=Contracts(self.registry)
        self.use_explicit = use_explicit
        self.use_reviewed=use_reviewed;self.use_policy=use_policy;self.use_hidden=use_hidden
        self.use_semantic=use_semantic;self.use_equations=use_equations
        self.use_linear_systems=use_linear_systems
        self.use_financial_graph=use_financial_graph
        self.cache: dict[str,tuple[dict[str,Any],dict[str,Any]]] = {}
        self.answer_cache: dict[str,tuple[dict[str,Any],dict[str,Any]]] = {}
        self.use_local_model=use_local_model;self.best_effort=None

    def predict(self, question: dict[str,Any]) -> tuple[dict[str,Any],dict[str,Any]]:
        """Export a complete answer for every valid question; never abstain."""
        key=hashlib.sha256(json.dumps(question,sort_keys=True).encode()).hexdigest()
        if key in self.answer_cache:return self.answer_cache[key]
        try:prediction,audit=self._predict_verified(question)
        except (KeyError,IndexError,ValueError,TypeError,ZeroDivisionError,OverflowError,SyntaxError,RecursionError) as exc:
            prediction={"schema_version":"finreason.task1.prediction/1.0.0","dataset_version":question["dataset_version"],"case_id":question["case_id"],"final_answer":None,"steps":[]}
            audit={'strategy':'verified_route_error','error':type(exc).__name__+': '+str(exc)}
        required={s['slot_id'] for s in question['trace_spec']['slots']}
        present={s['slot_id'] for s in prediction['steps']}
        if prediction['final_answer'] is not None and required<=present:
            self.answer_cache[key]=(prediction,audit);return prediction,audit
        if self.best_effort is None:
            from src.task1.best_effort import BestEffort
            self.best_effort=BestEffort(self.registry,use_local_model=self.use_local_model)
        fallback,extra=self.best_effort.predict(question)
        if prediction['final_answer'] is not None:
            fallback['final_answer']=prediction['final_answer']
            known={s['slot_id']:s for s in prediction['steps']}
            fallback['steps']=[known.get(s['slot_id'],s) for s in fallback['steps']]
            extra['preserved_final_strategy']=audit['strategy']
        extra['verified_route_audit']=audit
        self.answer_cache[key]=(fallback,extra);return fallback,extra

    def _predict_verified(self, question: dict[str,Any], *, _adapt_contract: bool=True) -> tuple[dict[str,Any],dict[str,Any]]:
        """Internal capability diagnostic; callers export through predict()."""
        from src.task1.report_percentage import solve_report_percentage
        report=solve_report_percentage(question)
        if report is not None:return report
        cache_key = hashlib.sha256(json.dumps(question,sort_keys=True).encode()).hexdigest()
        if cache_key in self.cache:return self.cache[cache_key]
        prediction = {"schema_version":"finreason.task1.prediction/1.0.0","dataset_version":question["dataset_version"],"case_id":question["case_id"],"final_answer":None,"steps":[]}
        # Preserve native competition outputs. Adapt only an identified trained
        # skeleton whose spelling or requested result/checkpoint contract changed.
        try:
            matched=self.contracts.match(question,self.registry)
            if matched is not None and _adapt_contract:
                source_signature,_,contract,_,_=matched
                try:raw_signature=bind(question['question'])[0]
                except (ValueError,ZeroDivisionError,OverflowError):raw_signature=None
                requested={key:question[key] for key in ['answer_spec','trace_spec']}
                if source_signature!=raw_signature or requested!=contract:
                    typed=self.contracts.solve(question,self.registry,use_reviewed=self.use_reviewed)
                    if typed is None:
                        typed=self.contracts.solve_canonical(question,self.registry,lambda canonical:self._predict_verified(canonical,_adapt_contract=False))
                    if typed is not None:
                        self.cache[cache_key]=typed;return typed
        except (ValueError,KeyError,TypeError,ZeroDivisionError,OverflowError):pass
        try:
            signature,bindings = bind(question["question"])
        except (ValueError,ZeroDivisionError,OverflowError) as exc:
            # Malformed numeric source text (for example 1/0) must not abort
            # an entire prediction batch before the bounded routes run.
            audit={"case_id":question["case_id"],"strategy":"abstain","question_sha256":cache_key,
                   "bindings":[],"binding_error":str(exc)}
            self.cache[cache_key]=(prediction,audit)
            return prediction,audit
        audit: dict[str,Any] = {"case_id":question["case_id"],"strategy":"abstain","question_sha256":cache_key,"bindings":[{"name":b.name,"text":b.text,"start":b.start,"end":b.end} for b in bindings]}
        from src.task1.policy_solver import solve_policy
        policy=solve_policy(question) if self.use_policy else None
        if policy is not None:
            audit['strategy']='fictional_policy';self.cache[cache_key]=(policy,audit);return policy,audit
        if self.use_policy:
            from src.task1.document_policy import solve_document_policy
            document=solve_document_policy(question)
            if document is not None:
                self.cache[cache_key]=document;return document
        if self.use_explicit:
            from src.task1.explicit_solver import solve_explicit
            explicit=solve_explicit(question)
            if explicit is not None:
                audit['strategy']='explicit_formula';self.cache[cache_key]=(explicit,audit);return explicit,audit
        program = self.registry.get(signature)
        if program is not None and len(bindings)==program["numeric_bindings"]:
            variables = {b.name:b.value for b in bindings}
            from src.task1.formulas import reviewed_program
            reviewed=reviewed_program(program['template_id']) if self.use_reviewed else None
            if reviewed is not None:program={**program,**reviewed};audit['strategy']='reviewed_financial_dag'
            audit["template_id"]=program["template_id"]
            audit["strategy"]="reviewed_financial_dag" if reviewed is not None else "induced_symbolic"
            try:
                for name,expression in program.get('dag',[]):variables[name]=execute(expression,variables)
                if program.get("final"):
                    prediction["final_answer"]={"value":format_value(execute(program["final"],variables),question["answer_spec"])}
                elif program.get("enum"):
                    enum=program["enum"];value=execute(enum["expression"],variables)
                    label=enum["labels"].get("positive" if value>0 else "negative" if value<0 else "zero")
                    if label is not None:prediction["final_answer"]={"value":label}
                for slot in question["trace_spec"]["slots"]:
                    expression=program["slots"].get(slot["slot_id"])
                    if expression:
                        value=execute(expression,variables)
                        rendered=('true' if value else 'false') if slot['result_spec']['type']=='enum' else format_value(value,slot['result_spec'])
                        prediction["steps"].append({"slot_id":slot["slot_id"],"value":rendered})
                    elif slot["slot_id"] in program.get("slot_enums",{}):
                        enum=program["slot_enums"][slot["slot_id"]];value=execute(enum["expression"],variables)
                        label=enum["labels"].get("positive" if value>0 else "negative" if value<0 else "zero")
                        if label is not None:prediction["steps"].append({"slot_id":slot["slot_id"],"value":label})
                audit["program"]=program
            except (ValueError,ZeroDivisionError,OverflowError) as exc:
                audit["execution_error"]=str(exc)
        if self.use_explicit and prediction["final_answer"] is None:
            from src.task1.explicit_solver import solve_explicit
            explicit=solve_explicit(question)
            if explicit is not None:
                # Preserve independently induced checkpoints absent from explicit.
                supplied={s["slot_id"] for s in explicit["steps"]}
                explicit["steps"].extend(s for s in prediction["steps"] if s["slot_id"] not in supplied)
                prediction=explicit;audit["strategy"]="explicit_formula"
        if self.use_hidden and prediction['final_answer'] is None:
            from src.task1.hidden_solver import solve_hidden
            alternate=solve_hidden(question)
            if alternate is not None:
                prediction=alternate;audit['strategy']='question_formula'
        # These strictly gated fallback routes never override an existing
        # non-null prediction, preserving the deployed 928-case candidate.
        if prediction['final_answer'] is None and self.use_semantic:
            from src.task1.semantic_router import solve_semantic
            semantic=solve_semantic(question)
            if semantic is not None:
                prediction,extra=semantic;audit.update(extra)
        if prediction['final_answer'] is None and self.use_equations:
            from src.task1.equation_fallback import solve_equations
            equations=solve_equations(question)
            if equations is not None:
                prediction,extra=equations;audit.update(extra)
            elif self.use_linear_systems:
                from src.task1.linear_system import solve_linear_system
                system=solve_linear_system(question)
                if system is not None:
                    prediction,extra=system;audit.update(extra)
        if prediction['final_answer'] is None and self.use_semantic and self.use_financial_graph:
            from src.task1.financial_graph import solve_financial_graph
            graph=solve_financial_graph(question)
            if graph is not None:
                prediction,extra=graph;audit.update(extra)
        if prediction['final_answer'] is None and self.use_semantic:
            from src.task1.currency_graph import solve_currency_graph
            currency=solve_currency_graph(question)
            if currency is not None:prediction,extra=currency;audit.update(extra)
        if prediction['final_answer'] is None and self.use_semantic:
            from src.task1.rate_relations import solve_rate_relations
            rates=solve_rate_relations(question)
            if rates is not None:prediction,extra=rates;audit.update(extra)
        if prediction['final_answer'] is None and self.use_semantic:
            from src.task1.series_program import solve_series
            series=solve_series(question)
            if series is not None:prediction,extra=series;audit.update(extra)
        self.cache[cache_key]=(prediction,audit)
        return prediction,audit
