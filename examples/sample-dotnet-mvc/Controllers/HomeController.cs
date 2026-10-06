using Microsoft.AspNetCore.Mvc;

namespace BookShelf.Controllers;

public class HomeController : Controller
{
    [HttpGet]
    public IActionResult Index()
    {
        return View();
    }
}
