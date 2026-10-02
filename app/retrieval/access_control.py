class AccessController:
    LEVELS = {
        "public": 0,
        "internal": 1,
        "admin": 2,
    }

    @staticmethod
    def _get_chunk(result):
        # Hybrid retrieval returns dictionaries, while dense/BM25 return
        # RetrievalResult Pydantic models. Support both representations.
        if isinstance(result, dict):
            return result.get("chunk")
        return getattr(result, "chunk", None)

    def filter_results(self, results, user_access_level):
        if user_access_level not in self.LEVELS:
            raise ValueError(
                f"Unknown access level: {user_access_level}"
            )

        user_level = self.LEVELS[user_access_level]

        filtered = []

        for result in results:
            chunk = self._get_chunk(result)

            # Fail closed if a retrieval result has no chunk.
            if chunk is None:
                continue

            if self.LEVELS.get(
                chunk.access_level,
                999,
            ) <= user_level:
                filtered.append(result)

        return filtered
