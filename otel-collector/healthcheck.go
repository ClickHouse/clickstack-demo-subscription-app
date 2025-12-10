package main

import "net/http"
import "os"

func main() {
  _, err := http.Get("http://localhost:13133")
  if err != nil {
    os.Exit(1)
  }
  os.Exit(0)
}
