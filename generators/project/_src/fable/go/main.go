// fable: runs a program of the Fable language read from standard input.
package main

import (
	"bufio"
	"fmt"
	"io"
	"os"
)

func run(src string) (out []string, status int) {
	it := newInterp()
	defer func() {
		if r := recover(); r != nil {
			e, ok := r.(*FableError)
			if !ok {
				panic(r)
			}
			out = append(it.out, fmt.Sprintf("error: line %d: %s", e.Line, e.Msg))
			status = 1
		}
	}()
	ast := (&Parser{toks: lex(src)}).program()
	it.runBlock(ast, it.globals, false)
	return it.out, 0
}

func main() {
	data, _ := io.ReadAll(bufio.NewReader(os.Stdin))
	out, status := run(string(data))
	w := bufio.NewWriter(os.Stdout)
	for _, l := range out {
		w.WriteString(l + "\n")
	}
	w.Flush()
	os.Exit(status)
}
