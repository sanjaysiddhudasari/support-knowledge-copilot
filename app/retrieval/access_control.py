class AccessController:
    LEVELS = {
        "public": 0,
        "internal": 1,
        "admin": 2,
    }

    def filter_results(self, results, user_access_level):
        if user_access_level not in self.LEVELS:
            raise ValueError(
                f"Unknown access level: {user_access_level}"
            )

        user_level = self.LEVELS[user_access_level]

        return [
            result
            for result in results
            if self.LEVELS.get(
                result["chunk"].access_level,
                -1,
            ) <= user_level
        ]