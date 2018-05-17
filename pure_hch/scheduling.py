from collections import deque
from typing import Deque, Dict, Generator, List, Optional, Set, Tuple

from .datastore import Address, Datastore
from .hypertext import Workspace

from .text_manipulation import create_raw_hypertext, insert_raw_hypertext


class Action(object):
    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:
        # Successor context should be first if action is deterministic;
        # otherwise it should be last.
        raise NotImplementedError("Action is pure virtual")


class AskSubquestion(Action):
    def __init__(self, question_text: str) -> None:
        self.question_text = question_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        subquestion_link = insert_raw_hypertext(
                self.question_text,
                db,
                context.inverse_display_map_for_workspace(current_workspace_link, db))

        answer_link = db.make_promise()
        sub_workspace_link = db.make_promise()

        current_workspace = db.dereference(current_workspace_link)

        new_subquestions = (current_workspace.subquestions +
                [(subquestion_link, answer_link, sub_workspace_link)])

        successor_workspace = Workspace(
                current_workspace.question_link,
                current_workspace.answer_link,
                current_workspace.scratchpad_link,
                new_subquestions,
                predecessor_link=current_workspace_link)

        successor_workspace_link = db.insert(successor_workspace)

        new_unlocked_locations = context.unlocked_locations_from_workspace(
                current_workspace_link, db)

        return (
                Context(
                    successor_workspace_link,
                    db,
                    unlocked_locations=new_unlocked_locations),
                [Context(sub_workspace_link, db)])


class Reply(Action):
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        current_workspace = db.dereference(current_workspace_link)
        return (
                None,
                db.resolve_promise(
                    current_workspace.answer_link,
                    create_raw_hypertext(
                        self.reply_text,
                        db,
                        context.inverse_display_map_for_workspace(
                            current_workspace_link,
                            db
                            )
                        )
                    )
                )



class Unlock(Action):
    def __init__(self, unlock_text: str) -> None:
        self.unlock_text = unlock_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:

        pointer_address = context.inverse_display_map_for_workspace(
                current_workspace_link,
                db
                )[self.unlock_text]

        new_unlocked_locations = context.unlocked_locations_from_workspace(
                current_workspace_link, db)

        new_unlocked_locations.add(pointer_address)

        successor_context = Context(
                current_workspace_link, db, unlocked_locations=new_unlocked_locations)

        if db.is_fulfilled(pointer_address):
            return (None, [successor_context])

        db.register_promisee(pointer_address, successor_context)
        return (None, [])




class Scratch(Action):
    def __init__(self, scratch_text: str) -> None:
        self.scratch_text = scratch_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            current_workspace_link: Address,
            ) -> Tuple[Optional[Context], List[Context]]:
        new_scratchpad_link = insert_raw_hypertext(
                self.scratch_text,
                db,
                context.inverse_display_map_for_workspace(current_workspace_link, db))
        current_workspace = db.dereference(current_workspace_link)
        successor_workspace = Workspace(
                current_workspace.question_link,
                current_workspace.answer_link,
                new_scratchpad_link,
                current_workspace.subquestions,
                predecessor_link=current_workspace_link)
        successor_workspace_link = db.insert(successor_workspace)

        new_unlocked_locations = context.unlocked_locations_from_workspace(
                current_workspace_link,
                db)

        return (
                Context(
                    successor_workspace_link,
                    db,
                    unlocked_locations=new_unlocked_locations),
                []
                )



class Context(object):
    def __init__(
            self,
            workspace_link: Address,
            db: Datastore,
            unlocked_locations: Optional[Set[Address]]=None,
            ) -> None:

        self.workspace_link = workspace_link
        workspace = db.dereference(workspace_link)

        if unlocked_locations is not None:
            self.unlocked_locations = unlocked_locations
        else:
            # All of the things that are visible in a context with no explicit unlocks.
            self.unlocked_locations = set(
                    [workspace_link, workspace.question_link, workspace.scratchpad_link] +
                    [q for q, a, w in workspace.subquestions] +
                    ([workspace.predecessor_link] if workspace.predecessor_link else []))
        self.display_map = self.build_display_maps(db)
        self.display = self.to_str(db)

    def _zip_to_workspace(
            self,
            workspace_link: Address,
            db: Datastore
            ) -> Generator[Tuple[Address, Address], None, None]:
        pass

    def unlocked_locations_from_workspace(
            self,
            workspace_link: Address,
            db: Datastore,
            ) -> Set[Address]:
        pass

    def inverse_display_map_for_workspace(
            self,
            workspace_link: Address,
            db: Datastore
            ) -> Dict[str, Address]:
        pass

    def build_display_maps(self, db: Datastore) -> Dict[Address, str]:
        pass

    def to_str(self, db: Datastore) -> str:
        pass

    def __str__(self) -> str:
        return self.display

    def __hash__(self) -> int:
        return hash(str(self))

    def __eq__(self, other: object) -> bool:
        if type(other) is not Context:
            return False
        return str(other) == str(self)


class Scheduler(object):
    def __init__(self, db: Datastore) -> None:
        self.db = db
        self.pending_contexts: Deque[Context] = deque()
        self.cache: Dict[Context, Action] = {}

    def ask_root_question(self, contents: str) -> None:
        question_link = insert_raw_hypertext(contents, self.db, {})
        answer_link = self.db.make_promise()
        scratchpad_link = self.db.make_promise()
        new_workspace = Workspace(question_link, answer_link, scratchpad_link, [])
        new_workspace_link = self.db.insert(new_workspace)
        self.pending_contexts.append(Context(new_workspace_link, self.db, set()))

    def resolve_action(self, context: Context, action: Action) -> None:
        self.cache[context] = action
        self.execute_action(context, action)

    def execute_action(self, context: Context, action: Action) -> None:
        resulting_contexts = action.execute(self.db, context, context.workspace_link)
        if resulting_contexts[0] is not None:
            self.pending_contexts.appendleft(resulting_contexts[0])

        self.pending_contexts.extend(resulting_contexts[1])

    def choose_context(self) -> Context:
        while self.pending_contexts[0] in self.cache:
            pending_context = self.pending_contexts.popleft()
            self.execute_action(pending_context, self.cache[pending_context])

        return self.pending_contexts.popleft()
