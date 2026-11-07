package acme.internal

uses com.guidewire.cc.system.SystemUtil

class HiddenPackageC {
  function boot() { SystemUtil.ping() }
}
