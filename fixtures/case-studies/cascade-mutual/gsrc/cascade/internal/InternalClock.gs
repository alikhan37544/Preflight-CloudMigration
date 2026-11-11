package cascade.internal

uses gw.internal.util.ClassLoaderUtil
uses com.guidewire.cc.system.SystemUtil

class InternalClock {
  function now() : String {
    ClassLoaderUtil.reload()
    return SystemUtil.currentTime()
  }
}
