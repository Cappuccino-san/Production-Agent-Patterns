"""Deterministic Mock LLM synthesizing Python computational code."""

class DeterministicMockLLM:
    """Generates Python scripts for code interpreter agent tasks."""

    def generate_code_for_task(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if "fibonacci" in prompt_lower:
            return """
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print(f"Fibonacci(10) = {fib(10)}")
"""
        elif "prime" in prompt_lower:
            return """
def is_prime(n):
    if n <= 1: return False
    for i in range(2, int(n**0.5) + 1):
        if n % i == 0: return False
    return True

primes = [x for x in range(2, 50) if is_prime(x)]
print(f"Primes up to 50: {primes}")
"""
        else:
            return """
# Standard computational task
data = [10, 20, 30, 40, 50]
mean_val = sum(data) / len(data)
print(f"Computed mean: {mean_val}")
"""
