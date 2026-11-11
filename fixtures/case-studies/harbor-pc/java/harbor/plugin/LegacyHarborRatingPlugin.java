package harbor.plugin;

import java.security.MessageDigest;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import java.util.HashMap;
import java.util.Map;

public class LegacyHarborRatingPlugin {
  private static Map<String, Double> cache = new HashMap<>();

  public String digest(String payload) throws Exception {
    MessageDigest md = MessageDigest.getInstance("MD5");
    Connection connection = DriverManager.getConnection("jdbc:harbor:rating");
    Statement statement = connection.createStatement();
    ResultSet rows = statement.executeQuery("SELECT factor FROM harbor_rating");
    return bytesToHex(md.digest(payload.getBytes())) + rows.getDouble(1);
  }

  private String bytesToHex(byte[] bytes) {
    return "";
  }
}
