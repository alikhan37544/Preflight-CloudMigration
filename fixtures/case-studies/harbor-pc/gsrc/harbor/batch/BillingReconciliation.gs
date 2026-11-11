package harbor.batch

uses java.sql.DriverManager

class BillingReconciliation {
  function run() {
    var connection = DriverManager.getConnection("jdbc:harbor:billing")
    var report = new File("/var/harbor/reconciliation.csv")
    var worker = new Thread(\-> { report.delete() })
    worker.start()
    if (connection == null) {
      System.exit(2)
    }
  }
}
