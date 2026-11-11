package cascade.plugin;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.HashMap;
import java.util.Map;

public class LegacyRatingPlugin {
  private static Map<String, Double> cache = new HashMap<>();

  public double rate(String vin) throws Exception {
    Connection connection = DriverManager.getConnection("jdbc:cascade:rating");
    Statement statement = connection.createStatement();
    ResultSet rows = statement.executeQuery("SELECT factor FROM cascade_rating");
    return rows.getDouble(1);
  }
}
