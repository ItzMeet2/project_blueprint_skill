using BookShelf.Data;
using BookShelf.Models;
using Microsoft.AspNetCore.Mvc;

namespace BookShelf.Controllers;

[Route("books")]
public class BooksController : Controller
{
    private readonly AppDbContext _db;

    public BooksController(AppDbContext db) => _db = db;

    [HttpGet("")]
    public IActionResult Index() => View(_db.Books.ToList());

    [HttpGet("{id}")]
    public IActionResult Details(int id) => View(_db.Books.Find(id));

    [HttpGet("create")]
    public IActionResult Create() => View();

    [HttpPost("create")]
    public IActionResult Create(Book book)
    {
        _db.Books.Add(book);
        _db.SaveChanges();
        return RedirectToAction("Index");
    }

    [HttpPost("{id}/delete")]
    public IActionResult Delete(int id)
    {
        var book = _db.Books.Find(id);
        if (book != null) _db.Books.Remove(book);
        _db.SaveChanges();
        return RedirectToAction("Index");
    }
}
