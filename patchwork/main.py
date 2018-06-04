import pickle
import sys

from .datastore import Datastore
from .scheduling import RootQuestionSession, Scheduler
from .interface import UserInterface
from .text_manipulation import make_link_texts


def main(argv):
    if len(argv) > 1:
        try:
            with open(argv[1], 'rb') as f:
                db, sched = pickle.load(f)
        except FileNotFoundError:
            db = Datastore()
            sched = Scheduler(db)
    else:
        db = Datastore()
        sched = Scheduler(db)
    print("What is your root question?")
    with RootQuestionSession(sched, input("> ")) as sess:
        if sess.is_fulfilled():
            print("That question has already been answered: ")
            print(make_link_texts(sess.final_answer_promise, db)[sess.final_answer_promise])
        else:
            ui = UserInterface(sess)
            ui.cmdloop()

    if len(argv) > 1:
        with open(argv[1], "wb") as f:
            pickle.dump((db, sched), f)

if __name__ == "__main__":
    main(sys.argv)

