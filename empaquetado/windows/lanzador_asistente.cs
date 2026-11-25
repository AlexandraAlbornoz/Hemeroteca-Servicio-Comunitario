// Asistente autónomo: extrae sus propios recursos y espera al cierre de la ventana.
using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Windows.Forms;
using System.Drawing;
using System.Collections.Generic;
using System.Web.Script.Serialization;

internal static class LanzadorAsistente
{
    // Valida cada ruta del paquete para impedir escrituras fuera de su carpeta temporal.
    private static string RutaSegura(string raiz, string relativa)
    {
        string ruta = Path.GetFullPath(Path.Combine(raiz, relativa));
        if (!ruta.StartsWith(raiz + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("El paquete contiene una ruta no válida.");
        return ruta;
    }

    // Ejecuta exclusivamente el asistente incluido, sin descargar componentes adicionales.
    [STAThread]
    private static int Main()
    {
        string temporal = Path.GetFullPath(Path.GetTempPath()).TrimEnd(Path.DirectorySeparatorChar);
        string carpeta = Path.GetFullPath(Path.Combine(temporal, "Hemeroteca-Asistente-" + Guid.NewGuid().ToString("N")));
        try
        {
            Directory.CreateDirectory(carpeta);
            Assembly programa = Assembly.GetExecutingAssembly();
            string modo;
            using (StreamReader lector = new StreamReader(programa.GetManifestResourceStream("modo.txt")))
                modo = lector.ReadToEnd().Trim();
            if (modo != "Instalar" && modo != "Desinstalar") throw new InvalidDataException("El asistente no está completo.");
            using (Stream recurso = programa.GetManifestResourceStream("paquete.zip"))
            using (ZipArchive paquete = new ZipArchive(recurso, ZipArchiveMode.Read))
            {
                foreach (ZipArchiveEntry archivo in paquete.Entries)
                {
                    string destino = RutaSegura(carpeta, archivo.FullName);
                    if (archivo.FullName.EndsWith("/")) { Directory.CreateDirectory(destino); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(destino));
                    using (Stream origen = archivo.Open())
                    using (FileStream salida = File.Create(destino)) origen.CopyTo(salida);
                }
            }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            using (Asistente ventana = new Asistente(carpeta, modo))
            {
                Application.Run(ventana);
                return ventana.CodigoSalida;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show("No se pudo abrir el asistente de Hemeroteca. Tus datos se conservan.\n\n" + error.Message,
                            "Hemeroteca", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        finally
        {
            // Solo elimina la carpeta temporal creada por esta ejecución, tras verificar
            // su ubicación absoluta. Nunca recibe rutas de datos ni de instalaciones.
            if (Path.GetDirectoryName(carpeta).Equals(temporal, StringComparison.OrdinalIgnoreCase) &&
                Path.GetFileName(carpeta).StartsWith("Hemeroteca-Asistente-", StringComparison.Ordinal))
            {
                try { Directory.Delete(carpeta, true); } catch (IOException) { } catch (UnauthorizedAccessException) { }
            }
        }
    }
}

// Ventana nativa con tres pasos y un trabajador separado para mantenerla activa.
internal sealed class Asistente : Form
{
    private readonly string carpeta, modo, directorio, informe;
    private readonly bool prueba, automatico;
    private int paso;
    private bool terminado, correcto;
    private Process proceso;
    private readonly Label titulo = new Label(), descripcion = new Label(), estado = new Label();
    private readonly Button siguiente = new Button(), cancelar = new Button(), atras = new Button();
    private readonly CheckBox escritorio = new CheckBox();
    private readonly ProgressBar progreso = new ProgressBar();
    private readonly Timer temporizador = new Timer();
    internal int CodigoSalida = 0;

    // Prepara textos, controles accesibles y ubicación de instalación de esta cuenta.
    internal Asistente(string recursos, string accion)
    {
        carpeta = recursos; modo = accion;
        string destinoPrueba = Environment.GetEnvironmentVariable("PERRI_INSTALACION_PRUEBA");
        prueba = !String.IsNullOrEmpty(destinoPrueba);
        automatico = prueba && Environment.GetEnvironmentVariable("PERRI_ASISTENTE_AUTOMATICO") == "1";
        directorio = prueba ? Path.GetFullPath(destinoPrueba) : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Hemeroteca-2.4.2-solo-consulta");
        informe = Path.Combine(carpeta, "estado.json");
        Text = (modo == "Instalar" ? "Instalar" : "Desinstalar") + " Hemeroteca 2.4.2 Solo consulta";
        ClientSize = new Size(780, 480); StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog; MaximizeBox = false;
        Font = new Font("Segoe UI", 10);
        Icon = new Icon(Path.Combine(carpeta, "recursos", "hemeroteca_periodico.ico"));
        PictureBox lateral = new PictureBox();
        lateral.SetBounds(0, 0, 194, 480); lateral.BackColor = Color.FromArgb(36, 76, 145);
        lateral.Image = Image.FromFile(Path.Combine(carpeta, "recursos", "asistente_lateral.bmp"));
        lateral.SizeMode = PictureBoxSizeMode.CenterImage; Controls.Add(lateral);
        titulo.SetBounds(224, 26, 530, 85); titulo.Font = new Font("Segoe UI", 21, FontStyle.Bold);
        titulo.ForeColor = Color.FromArgb(36, 76, 145); Controls.Add(titulo);
        descripcion.SetBounds(228, 118, 510, 190); Controls.Add(descripcion);
        escritorio.SetBounds(228, 310, 510, 28); escritorio.Text = "Crear un acceso directo en el escritorio";
        escritorio.Checked = true; Controls.Add(escritorio);
        progreso.SetBounds(228, 344, 510, 22); progreso.Visible = false; Controls.Add(progreso);
        estado.SetBounds(228, 371, 510, 35); Controls.Add(estado);
        atras.SetBounds(350, 429, 110, 33); atras.Text = "Atrás"; Controls.Add(atras);
        siguiente.SetBounds(470, 429, 130, 33); Controls.Add(siguiente);
        cancelar.SetBounds(610, 429, 130, 33); cancelar.Text = "Cancelar"; Controls.Add(cancelar);
        AcceptButton = siguiente; CancelButton = cancelar;
        atras.Click += delegate { paso = 0; MostrarPaso(); };
        siguiente.Click += delegate { Continuar(); };
        cancelar.Click += delegate { Close(); };
        temporizador.Interval = 200; temporizador.Tick += delegate { ConsultarEstado(); };
        FormClosing += AlCerrar;
        Shown += delegate { if (automatico) BeginInvoke(new Action(delegate { Continuar(); Continuar(); })); };
        MostrarPaso();
    }

    // Actualiza la bienvenida y la confirmación antes de modificar archivos.
    private void MostrarPaso()
    {
        atras.Visible = paso == 1; escritorio.Visible = paso == 1 && modo == "Instalar";
        if (paso == 0)
        {
            titulo.Text = modo == "Instalar" ? "Bienvenido a Hemeroteca" : "Desinstalar Hemeroteca";
            descripcion.Text = modo == "Instalar" ? "Tu hemeroteca, lista en pocos pasos.\r\n\r\nTodo lo necesario está incluido. Solo sigue los pasos del asistente.\r\n\r\nSe instalará una copia independiente.\r\n\r\nPulsa Siguiente para continuar." : "Este asistente retirará esta copia de Hemeroteca y conservará sus datos.\r\n\r\nCierra esta copia antes de continuar.";
            siguiente.Text = "Siguiente";
        }
        else
        {
            titulo.Text = modo == "Instalar" ? "Todo listo para instalar" : "Confirmar desinstalación";
            descripcion.Text = modo == "Instalar" ? "Se instalará para tu cuenta de Windows.\r\n\r\nPodrás abrir Hemeroteca desde el menú Inicio o el escritorio.\r\n\r\nLa instalación no cambiará tus contraseñas ni tus datos actuales." : "Se retirarán los archivos instalados de esta copia. Su colección y sus respaldos se conservarán.";
            siguiente.Text = modo;
        }
    }

    // Inicia un trabajador oculto; la ventana permanece disponible y muestra progreso.
    private void Continuar()
    {
        if (terminado) { Close(); return; }
        if (paso == 0) { paso = 1; MostrarPaso(); return; }
        if (paso != 1) return;
        paso = 2; siguiente.Enabled = cancelar.Enabled = false; atras.Visible = escritorio.Visible = false;
        progreso.Visible = true; titulo.Text = modo == "Instalar" ? "Instalando Hemeroteca" : "Desinstalando el programa";
        descripcion.Text = "Espera mientras Windows realiza la operación.";
        string argumentos = "-Modo " + modo + " -Directorio \"" + directorio + "\" -Informe \"" + informe + "\"";
        if (modo == "Instalar") argumentos += " -Paquete \"" + Path.Combine(carpeta, "programa") + "\"" + (escritorio.Checked ? " -Escritorio" : "");
        if (prueba) argumentos += " -Prueba";
        try { proceso = Ejecutar(Path.Combine(carpeta, "operaciones_instalacion.ps1"), argumentos); temporizador.Start(); }
        catch (Exception error) { Finalizar(false, error.Message); }
    }

    // Lee solo el progreso del trabajador y detecta fallos aunque no haya informe.
    private void ConsultarEstado()
    {
        if (File.Exists(informe))
        {
            try
            {
                Dictionary<string, object> datos = new JavaScriptSerializer().Deserialize<Dictionary<string, object>>(File.ReadAllText(informe));
                progreso.Value = Math.Max(0, Math.Min(100, Convert.ToInt32(datos["porcentaje"])));
                estado.Text = Convert.ToString(datos["mensaje"]);
                if (Convert.ToBoolean(datos["terminado"])) Finalizar(Convert.ToBoolean(datos["correcto"]), estado.Text);
            }
            catch (IOException) { } catch (ArgumentException) { }
        }
        if (!terminado && proceso != null && proceso.HasExited) Finalizar(false, "No se pudo completar la operación.");
    }

    // Presenta el resultado y permite finalizar; la prueba aislada se cierra sola.
    private void Finalizar(bool exito, string mensaje)
    {
        temporizador.Stop(); terminado = true; correcto = exito; CodigoSalida = exito ? 0 : 1;
        siguiente.Enabled = true; siguiente.Text = "Finalizar"; cancelar.Visible = false;
        titulo.Text = exito ? (modo == "Instalar" ? "Hemeroteca está lista" : "Programa desinstalado") : "No se pudo completar";
        descripcion.Text = exito ? (modo == "Instalar" ? "Puedes abrir Hemeroteca desde el menú Inicio o desde el escritorio.\r\n\r\nPara quitarla, busca Hemeroteca en Aplicaciones instaladas de Windows.\r\n\r\nPara conectar equipos, consulta LEEME_HEMEROTECA.txt en la carpeta instalada." : "Se retiró esta copia. Sus datos se conservan. Pulsa Finalizar para retirar el propio desinstalador.") : mensaje + "\r\n\r\nLa operación puede haber quedado incompleta. Corrige el error y vuelve a intentarlo.";
        if (automatico) Close();
    }

    // Ejecuta solamente scripts incluidos en el paquete, sin ventanas de consola.
    private static Process Ejecutar(string archivo, string argumentos)
    {
        string interprete = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
        ProcessStartInfo inicio = new ProcessStartInfo(interprete, "-NoProfile -NonInteractive -ExecutionPolicy RemoteSigned -File \"" + archivo + "\" " + argumentos);
        inicio.UseShellExecute = false; inicio.CreateNoWindow = true; inicio.WindowStyle = ProcessWindowStyle.Hidden;
        return Process.Start(inicio);
    }

    // Conserva evidencias de prueba y termina la eliminación del propio desinstalador.
    private void AlCerrar(object emisor, FormClosingEventArgs evento)
    {
        if (paso == 2 && !terminado) { evento.Cancel = true; return; }
        temporizador.Stop();
        string reporte = Environment.GetEnvironmentVariable("PERRI_INFORME_ASISTENTE");
        if (prueba && !String.IsNullOrEmpty(reporte) && File.Exists(informe)) File.Copy(informe, reporte, true);
        if (correcto && modo == "Desinstalar")
        {
            string limpieza = Path.Combine(Path.GetTempPath(), "Hemeroteca-Limpieza-" + Guid.NewGuid().ToString("N") + ".ps1");
            File.Copy(Path.Combine(carpeta, "limpiar_desinstalador.ps1"), limpieza);
            Ejecutar(limpieza, "-Directorio \"" + directorio + "\" -ProcesoEspera " + Process.GetCurrentProcess().Id);
        }
    }
}
