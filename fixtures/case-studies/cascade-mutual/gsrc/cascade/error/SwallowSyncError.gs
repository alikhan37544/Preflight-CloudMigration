package cascade.error

class SwallowSyncError {
  function sync() {
    try {
      maybeFail()
    } catch (e : Exception) {
      // ignored on purpose
    }
  }
}
