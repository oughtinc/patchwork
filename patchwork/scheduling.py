from collections import deque
from typing import Deque, Dict, Iterator, List, Optional, Set, Tuple, TypeVar, \
    Union

from .actions import Action
from .context import Context
from .datastore import Address, Datastore, TransactionAccumulator
from .hypertext import Workspace

from .text_manipulation import insert_raw_hypertext, make_link_texts


# Credits: Adapted from first_true in itertools docs.
T = TypeVar('T')
VT = TypeVar('VT')
def next_truthy(iterator: Iterator[T], default: VT) -> Union[T, VT]:
    """Return the next truthy value in ``iterator``.

    If no truthy value is found, return ``default``.
    """
    return next(filter(None, iterator), default)


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

# Some stuff about cycle detection:

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
# want to privilege `B -> C` or `C -> B` over the other. But in some sense you
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

# Yeah, I think the best thing to do is basically do all possible automation up front inside
# a transaction, as soon as an action is taken, letting bits throw exceptions if a cycle
# would be created. When that happens, we can discard the transaction; otherwise we commit it.


class Automator(object):
    def can_handle(self, context: Context) -> bool:
        raise NotImplementedError("Automator is pure virtual")

    def handle(self, context: Context) -> Action:
        raise NotImplementedError("Automator is pure virtual")


class Memoizer(Automator):
    def __init__(self):
        self.cache: Dict[Context, Action] = {}

    def remember(self, context: Context, action: Action):
        self.cache[context] = action

    def forget(self, context: Context):
        del self.cache[context]

    def can_handle(self, context: Context) -> bool:
        return context in self.cache

    def handle(self, context: Context) -> Action:
        return self.cache[context]


class Scheduler(object):
    def __init__(self, db: Datastore) -> None:
        self.db = db

        # Contexts that are currently being shown to a user
        self.active_contexts: Set[Context] = set()

        # Contexts that are waiting to be shown to a user because
        # they cannot be automated.

        # (note that these semantics mean that we must iterate over these contexts
        # every time the automatability criteria change)
        self.pending_contexts: Deque[Context] = deque([])

        # Things that can automate work - only the memoizer for now, though we could add
        # calculators, programs, macros, distilled agents, etc.
        self.memoizer = Memoizer()
        self.automators: List[Automator] = [self.memoizer]

    def ask_root_question(self, contents: str) -> Tuple[Context, Address]:
        # How root!
        question_link = insert_raw_hypertext(contents, self.db, {})
        answer_link = self.db.make_promise()
        final_workspace_link = self.db.make_promise()
        scratchpad_link = insert_raw_hypertext("", self.db, {})
        new_workspace = Workspace(question_link, answer_link, final_workspace_link, scratchpad_link, [])
        new_workspace_link = self.db.insert(new_workspace)
        result = Context(new_workspace_link, self.db)
        answer_link = self.db.dereference(result.workspace_link).answer_promise
        self.active_contexts.add(result)
        while self.memoizer.can_handle(result):
            result = self.resolve_action(result, self.memoizer.handle(result))

        return result, answer_link

    def resolve_action(self, starting_context: Context, action: Action) -> Optional[Context]:
        # NOTE: There's a lot of wasted work in here for the sake of rolling back cycle-driven mistakes.
        # This stuff could all be removed if we had budgets.
        assert starting_context in self.active_contexts
        transaction = TransactionAccumulator(self.db)
        self.memoizer.remember(starting_context, action)
        
        try:
            successor, other_contexts = action.execute(transaction, starting_context) 
            un_automatable_contexts: List[Context] = []
            possibly_automatable_contexts = deque(self.pending_contexts)
            possibly_automatable_contexts.extendleft(other_contexts)

            while len(possibly_automatable_contexts) > 0:
                context = possibly_automatable_contexts.popleft()
                automatic_action = None
                for automator in self.automators:
                    if automator.can_handle(context):
                        automatic_action = automator.handle(context)
                        break
                if automatic_action is not None:
                    new_successor, new_contexts = automatic_action.execute(transaction, context)
                    if new_successor is not None: # in the automated setting, successors are not special.
                        new_contexts.append(new_successor)
                    for context in new_contexts:
                        if context.is_own_ancestor(transaction): # So much waste
                            raise ValueError("Action resulted in an infinite loop")
                        possibly_automatable_contexts.append(context)
                else:
                    un_automatable_contexts.append(context)

            transaction.commit()
            self.pending_contexts = deque(un_automatable_contexts)
            self.active_contexts.remove(starting_context)
            if successor is not None:
                self.active_contexts.add(successor)
            return successor
        except:
            self.memoizer.forget(starting_context)
            raise

    def choose_context(self, promise: Address) -> Context:
        """Return a context that can advance ``promise``."""
        choice = next(c for c in self.pending_contexts
                      if c.can_advance_promise(self.db, promise))
        self.pending_contexts.remove(choice)
        self.active_contexts.add(choice)
        return choice

    def relinquish_context(self, context: Context) -> None:
        self.pending_contexts.append(context)
        self.active_contexts.remove(context)


class Session(object):
    def __init__(self, scheduler: Scheduler) -> None:
        self.sched = scheduler
         # current_context is None before and after the session is complete.
        self.current_context: Optional[Context] = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        # Handle cleanup. Things we need to do here:
        # Tell the scheduler that we relinquish our current context.
        if self.current_context is not None and self.current_context in self.sched.active_contexts:
            self.sched.relinquish_context(self.current_context)

    def act(self, action: Action) -> Union[Context, str]:
        raise NotImplementedError("Sessions must implement act()")


class RootQuestionSession(Session):
    # A root question session is only interested in displaying contexts
    # that are making progress toward its goal question. This is the only
    # kind of session the command line app, though there would be "aimless"
    # sessions in a real app.
    def __init__(self, scheduler: Scheduler, question: str) -> None:
        super().__init__(scheduler)
        self.current_context, self.root_answer_promise = \
            scheduler.ask_root_question(question)
        self.root_answer = None

        promise_to_advance = self.choose_promise(self.root_answer_promise)
        if promise_to_advance is None:  # Ie. everything was answered.
            self.format_root_answer()
        else:
            self.current_context = \
                self.current_context \
                or self.sched.choose_context(promise_to_advance)

    def choose_promise(self, root: Address) -> Optional[Address]:
        """Return unfulfilled promise from hypertext tree with root ``root``.

        Parameters
        ----------
        root
            Address pointing at hypertext or a promise of hypertext.

        Note
        ----
        Don't confuse the root node of a hypertext tree with the root question.

        Examples
        --------
        * If no reply was given to the root question yet, return the root
          question promise.
        * If the reply to the root question was given and is "To seek the
          Holy Grail.", return ``None``, because there is nothing left to do.
        * If the reply to the root question was given and is "Looks like a $a2."
          (from the perspective of the replier), return the promise that $a2
          points to. This is done recursively, so if $a2 is resolved to
          something that points to another promise p, return p.

        Purpose
        -------
        A hypertext object is *complete* when all its pointers are unlocked and
        the hypertext objects they point to are complete. Ie. "Looks like a
        [penguin]." and "What is your quest?" are complete, but "What is the
        capital of $1?" is not.

        After the root answer promise is resolved, the root answer might not yet
        be complete. The asker of the root question wants a complete answer, but
        she can't interact with it to unlock pointers. Instead, this method
        finds any promises that the root answer points to. The caller can then
        schedule contexts to resolve these promises.
        """
        if not self.sched.db.is_fulfilled(root):
            return root

        return next_truthy((self.choose_promise(child)
                            for child in self.sched.db.dereference(root).links()),
                           None)

    def format_root_answer(self) -> str:
        """Format the root answer with all its pointers unlocked."""
        self.root_answer = make_link_texts(
                                self.root_answer_promise,
                                self.sched.db)[self.root_answer_promise]
        return self.root_answer

    def act(self, action: Action) -> Union[Context, str]:
        resulting_context = self.sched.resolve_action(self.current_context,
                                                      action)

        promise_to_advance = self.choose_promise(self.root_answer_promise)
        if promise_to_advance is None:  # Ie. everything was answered.
            return self.format_root_answer()

        self.current_context = resulting_context \
                               or self.sched.choose_context(promise_to_advance)

        return self.current_context
