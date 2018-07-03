import pickle
import sys

from .datastore import Datastore
from .scheduling import RootQuestionSession, Scheduler
from .interface import UserInterface
from .text_manipulation import make_link_texts


def main(argv):
    if len(argv) > 1:
        fn = argv[1]
        try:
            with open(fn, 'rb') as f:
                db, sched = pickle.load(f)
        except FileNotFoundError:
            print("File '{}' not found, creating...".format(fn))
            db = Datastore()
            sched = Scheduler(db)
    else:
        db = Datastore()
        sched = Scheduler(db)
    print("What is your root question?")
    with RootQuestionSession(sched, input("> ")) as sess:
        if sess.root_answer:
            print("Could answer question immediately based on cached data: ")
            print(sess.root_answer)
        else:
            ui = UserInterface(sess)
            ui.cmdloop()

    if len(argv) > 1:
        with open(argv[1], "wb") as f:
            pickle.dump((db, sched), f)

if __name__ == "__main__":
    main(sys.argv)

