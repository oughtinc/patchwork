from typing import List, Optional, Tuple

from .context import Context, DryContext
from .datastore import Datastore
from .hypertext import Workspace
from .text_manipulation import create_raw_hypertext, insert_raw_hypertext

class Action(object):
    def execute(
            self,
            db: Datastore,
            context: Context,
            ) -> Tuple[Optional[Context], List[Context]]:
        # Successor context should be first if it exists.
        raise NotImplementedError("Action is pure virtual")


# Predictability here means "the user can predict what the successor looks like based only
# on the current workspace and the action taken." It's not very clear whether Reply should
# count or not, since it has no successor.
class PredictableAction(Action):
    pass


class UnpredictableAction(Action):
    pass


class Scratch(PredictableAction):
    def __init__(self, scratch_text: str) -> None:
        self.scratch_text = scratch_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            ) -> Tuple[Optional[Context], List[Context]]:

        new_scratchpad_link = insert_raw_hypertext(
                self.scratch_text,
                db,
                context.name_pointers_for_workspace(context.workspace_link, db))

        current_workspace = db.dereference(context.workspace_link)

        successor_workspace = Workspace(
                current_workspace.question_link,
                current_workspace.answer_promise,
                current_workspace.final_workspace_promise,
                new_scratchpad_link,
                current_workspace.subquestions,
                )

        successor_workspace_link = db.insert(successor_workspace)

        new_unlocked_locations = set(context.unlocked_locations_from_workspace(
                context.workspace_link,
                db))
        new_unlocked_locations.remove(context.workspace_link)
        new_unlocked_locations.add(successor_workspace_link)
        new_unlocked_locations.add(new_scratchpad_link)

        return (
                Context(
                    successor_workspace_link,
                    db,
                    unlocked_locations=new_unlocked_locations,
                    parent=context),
                []
                )


class AskSubquestion(PredictableAction):
    def __init__(self, question_text: str) -> None:
        self.question_text = question_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            ) -> Tuple[Optional[Context], List[Context]]:

        subquestion_link = insert_raw_hypertext(
                self.question_text,
                db,
                context.name_pointers_for_workspace(context.workspace_link, db))

        answer_link = db.make_promise()
        final_sub_workspace_link = db.make_promise()

        scratchpad_link = insert_raw_hypertext("", db, {})
        sub_workspace = Workspace(
                subquestion_link,
                answer_link,
                final_sub_workspace_link,
                scratchpad_link,
                [],
                )
        current_workspace = db.dereference(context.workspace_link)

        sub_workspace_link = db.insert(sub_workspace)
        sub_workspace = db.dereference(sub_workspace_link) # in case our copy was actually clobbered.

        new_subquestions = (current_workspace.subquestions +
                [(subquestion_link, sub_workspace.answer_promise, sub_workspace.final_workspace_promise)])
        successor_workspace = Workspace(
                current_workspace.question_link,
                current_workspace.answer_promise,
                current_workspace.final_workspace_promise,
                current_workspace.scratchpad_link,
                new_subquestions,
                )

        successor_workspace_link = db.insert(successor_workspace)

        new_unlocked_locations = set(context.unlocked_locations_from_workspace(
            context.workspace_link, db))
        new_unlocked_locations.remove(context.workspace_link)
        new_unlocked_locations.add(subquestion_link)
        new_unlocked_locations.add(successor_workspace_link)

        return (
                Context(
                    successor_workspace_link,
                    db,
                    unlocked_locations=new_unlocked_locations,
                    parent=context),
                [Context(sub_workspace_link, db, parent=context)])


class Reply(UnpredictableAction):
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            ) -> Tuple[Optional[Context], List[Context]]:

        current_workspace = db.dereference(context.workspace_link)

        reply_hypertext = create_raw_hypertext(
                self.reply_text,
                db,
                context.name_pointers_for_workspace(context.workspace_link, db))

        # final_workspace_promise and answer_promise aren't in
        # workspace.links(), so this is fine (doesn't create
        # link cycles).
        if not db.is_fulfilled(current_workspace.answer_promise):
            answer_successors = db.resolve_promise(current_workspace.answer_promise, reply_hypertext)
        else:
            answer_successors = []

        if not db.is_fulfilled(current_workspace.final_workspace_promise):
            workspace_successors = db.resolve_promise(
                    current_workspace.final_workspace_promise,
                    current_workspace)
        else:
            workspace_successors = []

        all_successors = [Context.from_dry(dry_context, db)
                for dry_context in answer_successors + workspace_successors]

        return (None, all_successors)


class Unlock(Action):
    def __init__(self, unlock_text: str) -> None:
        self.unlock_text = unlock_text

    def execute(
            self,
            db: Datastore,
            context: Context,
            ) -> Tuple[Optional[Context], List[Context]]:

        try:
            pointer_address = context.name_pointers_for_workspace(
                    context.workspace_link,
                    db
                    )[self.unlock_text]
        except KeyError:
            raise ValueError("{} is not visible in this context".format(self.unlock_text))

        new_unlocked_locations = set(context.unlocked_locations_from_workspace(
                context.workspace_link, db))

        if pointer_address in new_unlocked_locations:
            raise ValueError("{} is already unlocked.".format(self.unlock_text))

        new_unlocked_locations.add(pointer_address)

        dry_successor_context = DryContext(context.workspace_link,
                                           new_unlocked_locations, context)

        if db.is_fulfilled(pointer_address):
            return (None, [Context.from_dry(dry_successor_context, db)])

        db.register_promisee(pointer_address, dry_successor_context)
        return (None, [])

