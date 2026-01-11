
import asyncio
from fccs_agent.intelligence.intent_classifier import FCCSIntentClassifier

def test_classifier():
    classifier = FCCSIntentClassifier()
    query = "get app info"
    print(f"Classifying: {query}")
    intent = classifier.classify(query)
    print(f"Intent: {intent.name}")
    print(f"Entities: {intent.entities}")

if __name__ == "__main__":
    test_classifier()

