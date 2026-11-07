package acme.internal

uses gw.internal.util.ClassLoaderUtil
uses com.guidewire.cc.system.SystemUtil

class HiddenPackage {
  function boot() {
    ClassLoaderUtil.reload()
  }
}
