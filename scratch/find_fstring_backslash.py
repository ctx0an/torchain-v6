import os
import ast

repo_dir = r"e:\obsidian\vault\Torchain-main"

class FStringExpressionChecker(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        
    def visit_JoinedStr(self, node):
        for value in node.values:
            if isinstance(value, ast.FormattedValue):
                expr_src = ast.unparse(value.value)
                if "\\" in expr_src:
                    print(f"File: {self.filename}, Line: {value.lineno}")
                    print(f"  Expr: {{{expr_src}}}")
        self.generic_visit(node)

for root, dirs, files in os.walk(repo_dir):
    # Skip python caches and hidden folders
    dirs[:] = [d for d in dirs if not d.startswith((".", "__"))]
    for file in files:
        if file.endswith(".py"):
            filepath = os.path.join(root, file)
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read(), filename=filepath)
                    checker = FStringExpressionChecker(os.path.relpath(filepath, repo_dir))
                    checker.visit(tree)
                except Exception as e:
                    print(f"Failed to parse {file}: {e}")

print("Repository verification complete.")
