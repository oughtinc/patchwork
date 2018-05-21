import logging

from collections import defaultdict, deque
from textwrap import indent
from typing import Callable, DefaultDict, Deque, Dict, Generator, List, Optional, Set, Tuple

from .actions import Action, PredictableAction, UnpredictableAction, SuperAction
from .context import Context
from .datastore import Datastore
from .hypertext import Workspace

from .text_manipulation import insert_raw_hypertext

# What is the scheduler's job, what is the automator's job, and what is the session's job?
# Well, it seems like the session should know which contexts are "active", at least, and
# therefore which ones are available to be worked on.

# The scheduler also needs to be responsible for coordinating automators, which means that
# when a session records an action, the scheduler needs to check to see whether that action
# will create a cycle, and only actually perform the action if it does not create a cycle.
# This seems kind of scary since action execution (right now) can modify the state of the
# database by fulfilling real promises. This cannot then be undone.  Maybe a better solution
# here would be for action execution to return a representation of their effects instead.
# I think promise fulfilment is the only scary thing here, though? Scratchpad editing seems
# straightforwardly fine, asking subquestions is scary from the perspective of
# "we might accidentally automate something that produces an infinite loop of subquestions" but
# is not scary if you avoid that problem (you might end up with some uncollected garbage
# in the datastore, but no infinite loops due to the workspace itself. Forgotten workspaces are
# forgotten, and they don't prescribe any actions).

# An automator clearly has to have a method which accepts a context and produces something.
# Should it produce contexts? This seems plausible to me. However it could instead produce some
# form of actions.

class Automator(object):
    def can_handle(self, context: Context) -> bool:
        raise NotImplementedError("Automators must implement can_handle")

    def handle(self, context: Context) -> List[Context]:
        raise NotImplementedError("Automators must implement handle")

class Memoizer(Automator):
    def __init__(self):
        self.cached_action_sequences: Dict[Context, SuperAction] = {}

    def can_handle(self, context: Context) -> bool:
        return context in self.cached_action_sequences

    def handle(self, context: Context) -> List[Context]:
        pass

    def register_superaction(self, context: Context, action: SuperAction):
        pass


class Scheduler(object):
    def __init__(self, db: Datastore) -> None:
        self.db = db
        self.active_contexts: Set[Context] = set()
        self.automators: List[Automator] = [Memoizer()]


    def ask_root_question(self, contents: str) -> Context:
        question_link = insert_raw_hypertext(contents, self.db, {})
        answer_link = self.db.make_promise()
        final_workspace_link = self.db.make_promise()
        scratchpad_link = insert_raw_hypertext("", self.db, {})
        new_workspace = Workspace(question_link, answer_link, final_workspace_link, scratchpad_link, [])
        new_workspace_link = self.db.insert(new_workspace)
        return Context(new_workspace_link, self.db)

    def does_action_produce_cycle(self, context: Context, action: Action) -> bool:
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

        # It seems likely to me that there will be very counter-intuitive examples where
        # taking an action would produce a cycle. I can't think of any as I'm writing this,
        # but I'm imagining it would involve complicated use of pointers and scratchpads.
        
        return False

    def resolve_action(self, starting_context: Context, action: Action) -> None:
        assert starting_context in self.active_contexts

        pending_actions = deque([(context, action)])

        new_fulfilments = []
        new_contexts = []

        while len(pending_actions) > 0:
            next_context, next_action = pending_actions.popleft()
            action.execute()

    def choose_context(self) -> Optional[Context]:
        pass

    def relinquish_context(self, context: Context) -> None:
        pass


class Session(object):
    def __init__(self, scheduler: Scheduler) -> None:
        self.sched = scheduler
         # current_context is None before and after the session is complete.
        self.current_context: Optional[Context] = None

    def __enter__(self):
        if not self.current_context:
            self.current_context = self.sched.acquire_context()
        return self

    def __exit__(self, *args):
        # Handle cleanup. Things we need to do here:
        # Tell the scheduler that we relinquish our current context.
        if self.current_context is not None:
            self.sched.relinquish_context(self.current_context)

    def current_context(self) -> Optional[Context]:
        return self.current_context

    def act(self, action: Action) -> Optional[Context]:
        raise NotImplementedError("Sessions must implement act()")


class RootQuestionSession(Session):
    # A root question session is only interested in displaying contexts
    # whose answers have been unlocked by its root context, or contexts whose
    # answers have been unlocked by 
    def __init__(self, scheduler: Scheduler, question: str) -> None:
        super().__init__(scheduler)

class AimlessSession(Session):
    # An aimless session is happy to display any context until there are none left
    pass
