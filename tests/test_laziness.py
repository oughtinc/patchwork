import unittest

from patchwork.actions import Unlock, AskSubquestion
from patchwork.datastore import Datastore
from patchwork.scheduling import RootQuestionSession, Scheduler


class LazinessTest(unittest.TestCase):
    def testLaziness(self):
        """
        Schedule context for which unlock is waiting, not top-of-stack context.
        """
        db = Datastore()
        sched = Scheduler(db)

        with RootQuestionSession(sched, "Root question?") as sess:
            sess.act(AskSubquestion("Question 1?"))
            sess.act(AskSubquestion("Question 2?"))
            sess.act(AskSubquestion("Question 3?"))
            sess.act(AskSubquestion("Question 4?"))
            context = sess.act(Unlock("$a2"))
            self.assertIn("Question 2?", str(context))
