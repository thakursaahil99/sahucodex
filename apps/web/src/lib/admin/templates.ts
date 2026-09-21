/** Generic stdin → stdout skeletons an admin can start a problem's starter code from. */
export const STARTER_TEMPLATES: Record<string, string> = {
  python: `import sys


def solve(data: str) -> str:
    # TODO: parse \`data\`, compute the answer, and return the text to print.
    return ""


if __name__ == "__main__":
    sys.stdout.write(solve(sys.stdin.read()))
`,
  cpp: `#include <bits/stdc++.h>
using namespace std;

int main() {
    ios::sync_with_stdio(false);
    cin.tie(nullptr);
    // TODO: read the input, compute the answer and print it.
    return 0;
}
`,
  javascript: `const data = require("fs").readFileSync(0, "utf8");

function solve(data) {
  // TODO: parse \`data\`, compute the answer, and return the text to print.
  return "";
}

process.stdout.write(solve(data));
`,
};
