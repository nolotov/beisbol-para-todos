__version__ = "0.10.0"

# Solo generamos imágenes a archivo: forzamos el backend "Agg" (sin ventanas).
# En Windows matplotlib escoge TkAgg por defecto y falla si Tcl/Tk no está bien instalado.
import matplotlib

matplotlib.use("Agg")
