package acme.error

class SwallowErrorB {
  function risky() {
    try { maybeFail() } catch (e : Exception) { }
  }
}
