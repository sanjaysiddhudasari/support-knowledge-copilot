import re
import time
from pathlib import Path
import joblib

from rank_bm25 import BM25Okapi
from app.models.retrieval import RetrievalResult
from app.observability.tracing import describe_result, span


class BM25Retriever:

    def __init__(self):
        self.bm25 = None
        self.chunks = []

    def build_index(self, chunks):
        self.chunks = chunks

        tokenized_chunks = [
            self._tokenize(chunk.text)
            for chunk in chunks
        ]

        self.bm25 = BM25Okapi(tokenized_chunks)


    def save(self,path:str):
         file_path=Path(path)

         file_path.parent.mkdir(parents=True, exist_ok=True)

         joblib.dump(
              {
                   "bm25":self.bm25,
                   "chunks":self.chunks
              },
              file_path
         )


    def load(self,path:str):
         data=joblib.load(path)

         self.bm25=data["bm25"]
         self.chunks=data["chunks"]



    def retrieve(self, query: str, top_k: int = 5):

            if self.bm25 is None:
                raise RuntimeError(
                    "BM25 index has not been built."
                )

            started = time.perf_counter()

            with span(
                "BM25 Retrieval",
                run_type="retriever",
                tags=["rag", "bm25"],
                metadata={
                    "retrieval_type": "bm25",
                    "top_k": top_k,
                    "indexed_chunks": len(self.chunks),
                },
                inputs={"query": query},
            ) as run:

                query_tokens = self._tokenize(query)

                scores = self.bm25.get_scores(query_tokens)

                ranked_indices = sorted(
                    range(len(scores)),
                    key=lambda i: scores[i],
                    reverse=True,
                )[:top_k]

                results = [
                    RetrievalResult(
                        chunk=self.chunks[i],
                        score=float(scores[i]),
                        rank=rank,
                        source="bm25",
                    )
                    for rank, i in enumerate(ranked_indices, start=1)
                ]

                run.add_metadata(
                    {
                        "result_count": len(results),
                        "latency_ms": round(
                            (time.perf_counter() - started) * 1000, 2
                        ),
                    }
                )

                run.add_outputs(
                    {
                        "retrieved": [
                            describe_result(result)
                            for result in results
                        ]
                    }
                )

                return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return re.findall(
            r"\b\w+\b",
            text.lower(),
        )
