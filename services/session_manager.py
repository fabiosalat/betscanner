class SessionManager:
    def __init__(self, betfair_service):
        self.betfair = betfair_service
    def login(self): return self.betfair.login()
    def keep_alive(self): return self.betfair.keep_alive()
    def reconnect(self):
        self.betfair.trading = None
        return self.betfair.login()
