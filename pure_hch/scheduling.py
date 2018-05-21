import logging

from collections import defaultdict, deque
from textwrap import indent
from typing import Callable, DefaultDict, Deque, Dict, Generator, List, Optional, Set, Tuple

from .actions import Action
from .context import Context
from .datastore import Datastore
from .hypertext import Workspace

from .text_manipulation import insert_raw_hypertext


class Scheduler(object):
    # TODO
    # The scheduler is the main thing that needs to be rethought to make it
    # compatible with a webapp-style framework.
    # It also currently does no cycle checking (see `does_action_produce_cycle`).
    def __init__(self, initial_question: str, db: Datastore) -> None:
        self.db = db
        # The scheduler is, at almost any moment, in the middle
        # of a non-branching sequence of actions.

        # There should always be a current context, a last branching context
        # (which can be the same), and a list of actions that have been taken
        # since the last branching context.
        self.last_branching_context = self.ask_root_question(initial_question)
        self.current_context: Optional[Context] = self.last_branching_context
        self.unbranched_actions: List[Action] = []
        self.cache: Dict[Context, List[Action]] = {}
        self.branches: Deque[Context] = deque()

    def ask_root_question(self, contents: str) -> Context:
        question_link = insert_raw_hypertext(contents, self.db, {})
        answer_link = self.db.make_promise()
        final_workspace_link = self.db.make_promise()
        scratchpad_link = insert_raw_hypertext("", self.db, {})
        new_workspace = Workspace(question_link, answer_link, final_workspace_link, scratchpad_link, [])
        new_workspace_link = self.db.insert(new_workspace)
        return Context(new_workspace_link, self.db)

    def does_action_produce_cycle(self, context: Context, action: Action) -> bool:
        # TODO

        # Hm. What kind of cycles actually matter?

        # Budgets should circumvent this problem.

        # It's actually fine to produce a subquestion that _looks_ identical to the 
        # parent question, and in fact this is one way automation can work at all.
        # It's only not fine to produce a subquestion that _is_ the same as a parent
        # question, down to... what, exactly? Obviously ending up with a workspace
        # who's its own ancestor in the subquestion graph is bad. But you can end up
        # with this situation in annoying ways.

        # `A -> B [1] -> C -> B [2]` is fine.
        # `A -> B -> C -> B` is not.

        # But imagine you actually get `A -> (B, C)`, `B -> C`, and `C -> B`. You don't
        # want to privelege `B -> C` or `C -> B` over the other. But in some sense you
        # have to: You can't block actions, or else you have to sometimes show a user a
        # random error message.

        # So you have to present the temporally _second_ creator of `B -> C` or `C -> B`
        # the error message immediately (this is an unfortunate but necessary "side channel").
        # The problem that _this_ produces is that `C -> B` may be created _automatically_.

        # Imagine that you have previously seen that `A -> B [(locked) 1] -> C`. So you stored
        # that `B $1` produces `ask C`. But now you see that `C -> B [(locked) 2]`.
        # `B [(locked) 2]` is a different workspace from `B $1`, so the naive workspace-based
        # checking doesn't notice anything wrong until it tries to look at actions produced by
        # `C`, at which time it's too late (since C has already been scheduled). There is now
        # no way out of the trap.

        # I _think_ that you instead need to do the checking based on contexts: When you perform
        # an action, if you did all the automated steps this action implies, would you end up
        # with any copies of your starting workspace?

        # This implies a sort of automation-first approach that is pretty different from the
        # original way I wrote the scheduler, and might produce a much slower user experience
        # if the system gets big and highly automated.

        # It seems possible to me that sometimes there will be very counter-intuitive examples
        # where taking an action would produce a cycle. I can't think of any, but I'm imagining
        # it would involve complicated use of pointers and scratchpads.
        
        return False

    def resolve_action(self, action: Action) -> None:
        assert self.current_context is not None
        if self.does_action_produce_cycle(self.current_context, action):
            raise ValueError("Action would produce a cycle in the context graph")
        if action.predictable():
            self.execute_predictable_action(action)
        else:
            self.execute_unpredictable_action(action)

    def execute_predictable_action(self, action: Action) -> None:
        assert self.current_context is not None
        self.current_context, others = action.execute(self.db, self.current_context)
        self.unbranched_actions.append(action)
        self.branches.extend(others)

    def execute_unpredictable_action(self, action: Action) -> None:
        assert self.current_context is not None

        _, branches = action.execute(self.db, self.current_context)
        self.unbranched_actions.append(action)

        self.cache[self.last_branching_context] = self.unbranched_actions
        self.unbranched_actions = []

        self.branches.extend(branches)

        while len(self.branches) > 0 and self.branches[-1] in self.cache:
            next_context = self.branches.pop()
            for next_action in self.cache[next_context]:
                successor, others = next_action.execute(self.db, next_context)
                self.branches.extend(others)
                if successor is None:
                    break
                next_context = successor
        
        if len(self.branches) == 0:
            self.current_context = None
        else:
            self.current_context = self.branches.pop()
            self.last_branching_context = self.current_context
