package cascade.cache

class RatingCache {
  private static var factors : java.util.Map = new java.util.HashMap()
  static var lastTenant : String = null

  function remember(tenant : String, factor : double) {
    lastTenant = tenant
    factors.put(tenant, factor)
  }
}
