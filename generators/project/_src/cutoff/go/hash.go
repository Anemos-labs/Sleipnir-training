package main

import "fmt"

// digest is FNV-1a (32 bit) over the bytes of the text, as eight lower-case hex digits.
func digest(text string) string {
	h := uint32(0x811C9DC5)
	for i := 0; i < len(text); i++ {
		h ^= uint32(text[i])
		h *= 0x01000193
	}
	return fmt.Sprintf("%08x", h)
}
