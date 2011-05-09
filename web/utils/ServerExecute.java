import com.gargoylesoftware.htmlunit.WebClient;
import com.gargoylesoftware.htmlunit.html.HtmlPage;

public class ServerExecute {
	public static void main(String[] args) {
		if (args.length != 1) {
			System.err.println("You must give a url as an argument.");
			return;
		}
		try {
			final WebClient webClient = new WebClient();
			HtmlPage page = webClient.getPage(args[0]);
			webClient.waitForBackgroundJavaScript(2000);
			System.out.println(page.asXml());
		} catch (Exception e) {
			e.printStackTrace();
		}
	}
}
