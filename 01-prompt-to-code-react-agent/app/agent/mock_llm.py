"""Deterministic offline mock LLM engine for ReAct code generation."""

from typing import Callable, Optional


class DeterministicMockLLM:
    """Predictable mock LLM enabling offline, deterministic ReAct reasoning and code generation."""

    def __init__(
        self,
        override_responses: Optional[list[dict[str, str]]] = None,
        custom_generator: Optional[Callable[[str, int, Optional[str]], tuple[str, str]]] = None,
    ):
        self.override_responses = list(override_responses) if override_responses else []
        self.custom_generator = custom_generator
        self.call_history: list[dict[str, str]] = []

    def reason_and_generate(
        self,
        prompt: str,
        iteration: int,
        error: Optional[str] = None,
    ) -> tuple[str, str]:
        """Generate thought analysis and synthesized Python code."""
        self.call_history.append({"prompt": prompt, "iteration": str(iteration), "error": str(error)})

        # 1. Custom generator if provided
        if self.custom_generator:
            return self.custom_generator(prompt, iteration, error)

        # 2. Sequential overrides if provided
        if self.override_responses:
            item = self.override_responses.pop(0)
            thought = item.get("thought", f"Thought: Applying preset response for iteration {iteration}")
            code = item.get("code", "# Default code\nprint('OK')")
            return thought, code

        # 3. Simulate syntax error recovery if prompted
        if "simulate_syntax_error" in prompt.lower() and iteration == 1 and not error:
            thought = "Thought: Deliberately synthesizing code with missing parenthesis to test AST validation."
            code = "def calculate_total(a, b):\n    return a + b\n\nprint(calculate_total(10, 20"
            return thought, code

        if error:
            thought = f"Thought: Detected syntax issue '{error}'. Fixing syntax and re-synthesizing clean Python code."
            # Recover from syntax error
            code = (
                "def calculate_total(a, b):\n"
                "    return a + b\n\n"
                "result = calculate_total(10, 20)\n"
                "print(f'Total: {result}')\n"
            )
            return thought, code

        # 4. Domain-specific rule-based code generation
        lower = prompt.lower()
        if "fibonacci" in lower:
            thought = "Thought: Requirements specify Fibonacci series. Generating iterative implementation with base cases."
            code = (
                "def fibonacci(n: int) -> list[int]:\n"
                "    if n <= 0:\n"
                "        return []\n"
                "    if n == 1:\n"
                "        return [0]\n"
                "    seq = [0, 1]\n"
                "    while len(seq) < n:\n"
                "        seq.append(seq[-1] + seq[-2])\n"
                "    return seq\n\n"
                "if __name__ == '__main__':\n"
                "    result = fibonacci(8)\n"
                "    print(f'Fibonacci: {result}')\n"
            )
        elif "factorial" in lower:
            thought = "Thought: Requirements specify factorial computation. Implementing recursive factorial function."
            code = (
                "def factorial(n: int) -> int:\n"
                "    if n < 0:\n"
                "        raise ValueError('Negative inputs undefined')\n"
                "    if n in (0, 1):\n"
                "        return 1\n"
                "    return n * factorial(n - 1)\n\n"
                "if __name__ == '__main__':\n"
                "    print(f'Factorial(5): {factorial(5)}')\n"
            )
        elif "prime" in lower:
            thought = "Thought: Generating primality checker function."
            code = (
                "def is_prime(n: int) -> bool:\n"
                "    if n < 2:\n"
                "        return False\n"
                "    for i in range(2, int(n ** 0.5) + 1):\n"
                "        if n % i == 0:\n"
                "            return False\n"
                "    return True\n\n"
                "if __name__ == '__main__':\n"
                "    print(f'Is 17 prime? {is_prime(17)}')\n"
            )
        elif "reverse" in lower:
            thought = "Thought: String reversal algorithm requested. Generating reverse_string function."
            code = (
                "def reverse_string(text: str) -> str:\n"
                "    return text[::-1]\n\n"
                "if __name__ == '__main__':\n"
                "    print(f'Reversed: {reverse_string(\"AgenticAI\")}')\n"
            )
        else:
            thought = f"Thought: Analyzing request '{prompt[:40]}...'. Synthesizing Python solution."
            code = (
                f"# Generated code for: {prompt[:60]}\n"
                "def execute_task():\n"
                "    message = 'Execution succeeded'\n"
                "    return message\n\n"
                "if __name__ == '__main__':\n"
                "    print(execute_task())\n"
            )

        return thought, code
