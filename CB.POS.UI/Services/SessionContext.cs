using CB.POS.Core.Entities;
using CB.POS.Core.Interfaces.Services;

namespace CB.POS.UI.Services;

public class SessionContext : ISessionContext
{
    public Employee? CurrentEmployee { get; private set; }

    public void SetAuthentication(Employee employee)
    {
        CurrentEmployee = employee;
    }

    public void Logout()
    {
        CurrentEmployee = null;
    }
}
