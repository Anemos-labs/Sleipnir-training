"""Per-language conventions: the verify command, project skeleton helpers, source extensions.

All commands run offline in a clean checkout with the toolchains installed here (Go 1.25, Python 3.11, Node 22,
Rust/cargo, Java 17+, gcc, Ruby, PHP, tsc, bash). Tasks must not need a package installed from the network.
"""
from __future__ import annotations

VERIFY = {
    "python": "python3 -m unittest discover -s tests -v",
    "go": "go test -count=1 ./...",
    "javascript": "node --test test/",
    "typescript": "rm -rf build && tsc -p . && node --test build/test/",
    "rust": "cargo test --offline --quiet",
    "java": "rm -rf build && mkdir -p build && javac -d build $(find . -name '*.java') && java -cp build TestMain",
    "c": "mkdir -p build && gcc -std=c11 -O1 -Wall -Wextra -o build/tests $(find src tests -name '*.c') && ./build/tests",
    "cpp": "mkdir -p build && g++ -std=c++17 -O1 -Wall -Wextra -o build/tests $(find src tests -name '*.cpp') && ./build/tests",
    "ruby": "ruby -Ilib -Itest -e 'Dir[\"test/test_*.rb\"].sort.each { |f| require \"./#{f}\" }'",
    "php": "php tests/run.php",
    "bash": "bash tests/run.sh",
}

EXT = {
    "python": ".py", "go": ".go", "javascript": ".js", "typescript": ".ts", "rust": ".rs", "java": ".java",
    "c": ".c", "cpp": ".cpp", "ruby": ".rb", "php": ".php", "bash": ".sh",
}

GITIGNORE = {
    "python": "__pycache__/\n*.pyc\n",
    "go": "",
    "javascript": "node_modules/\n",
    "typescript": "node_modules/\nbuild/\n",
    "rust": "target/\n",
    "java": "build/\n",
    "c": "build/\n",
    "cpp": "build/\n",
    "ruby": "",
    "php": "",
    "bash": "",
}


def go_mod(name: str, go: str = "1.21") -> str:
    return f"module example.com/{name}\n\ngo {go}\n"


def cargo_toml(name: str, edition: str = "2021") -> str:
    return f'[package]\nname = "{name}"\nversion = "0.1.0"\nedition = "{edition}"\n\n[dependencies]\n'


def tsconfig() -> str:
    return (
        '{\n  "compilerOptions": {\n    "target": "ES2022",\n    "module": "commonjs",\n    "outDir": "build",\n'
        '    "rootDir": ".",\n    "strict": true,\n    "types": ["node"],\n    "skipLibCheck": true\n  },\n'
        '  "include": ["src/**/*.ts", "test/**/*.ts"]\n}\n'
    )
