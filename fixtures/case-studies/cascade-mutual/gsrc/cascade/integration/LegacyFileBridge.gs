package cascade.integration

class LegacyFileBridge {
  function writeFeed() {
    var directory = new File("/opt/cascade/dealer-feed")
    new Thread(\-> { directory.list() }).start()
    System.exit(1)
  }
}
